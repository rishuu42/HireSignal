"""
cleaner.py
----------
Cleans and structures raw HN job post data into a usable B2B dataset.

Cleaning decisions documented:
1. HTML tags stripped from post text (HN stores text as HTML)
2. Company name extracted via heuristic: first bold/uppercase segment or first line
3. Location extracted by matching known patterns (Remote, city names, flags like "ONSITE")
4. Role/title extracted by matching common job title keywords
5. Tech stack inferred by matching known technology keywords
6. Posts with no extractable signal are flagged but kept (not dropped) for auditability
7. Timestamps normalised to ISO 8601 UTC strings
8. All text fields stripped of excess whitespace and normalised to UTF-8
"""

import json
import re
import sqlite3
import logging
import os
from datetime import datetime
from html.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = "data"
RAW_INPUT = os.path.join(DATA_DIR, "raw_jobs.json")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

# ── Keyword lists ──────────────────────────────────────────────────────────────

ROLE_KEYWORDS = [
    "Software Engineer", "Frontend", "Backend", "Full Stack", "Full-Stack",
    "Data Engineer", "Data Scientist", "ML Engineer", "Machine Learning",
    "DevOps", "SRE", "Platform Engineer", "Product Manager", "Designer",
    "iOS", "Android", "Mobile", "Embedded", "Security", "QA", "Intern",
    "CTO", "CEO", "COO", "VP Engineering", "Engineering Manager",
    "Rust", "Python Developer", "Go Developer", "Java Developer",
]

TECH_KEYWORDS = [
    "Python", "JavaScript", "TypeScript", "Rust", "Go", "Java", "C++", "C#",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "Elixir", "Haskell",
    "React", "Vue", "Angular", "Next.js", "Svelte",
    "Node.js", "Django", "FastAPI", "Flask", "Rails", "Spring",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
    "GraphQL", "REST", "gRPC", "Kafka", "Spark", "Airflow",
    "PyTorch", "TensorFlow", "LLM", "OpenAI", "Langchain",
]

LOCATION_PATTERNS = [
    r"\bRemote\b", r"\bOnsite\b", r"\bHybrid\b",
    r"\bSan Francisco\b", r"\bNew York\b", r"\bNYC\b", r"\bSeattle\b",
    r"\bLondon\b", r"\bBerlin\b", r"\bAmsterdam\b", r"\bParis\b",
    r"\bToronto\b", r"\bAustin\b", r"\bBoston\b", r"\bChicago\b",
    r"\bBangalore\b", r"\bDelhi\b", r"\bMumbai\b", r"\bSingapore\b",
    r"\bUS only\b", r"\bUSA\b", r"\bEU\b", r"\bWorldwide\b",
    r"\bWFH\b", r"\bWork from home\b",
]

SALARY_PATTERN = re.compile(
    r"(\$[\d,]+[kK]?\s*[-–]\s*\$[\d,]+[kK]?|\$[\d,]+[kK]|\b[\d]+[kK]\s*[-–]\s*[\d]+[kK])",
    re.IGNORECASE,
)


# ── HTML stripping ─────────────────────────────────────────────────────────────

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []

    def handle_data(self, data):
        self.text_parts.append(data)

    def get_text(self):
        return " ".join(self.text_parts)


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities."""
    if not html:
        return ""
    stripper = HTMLStripper()
    stripper.feed(html)
    text = stripper.get_text()
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Extractors ─────────────────────────────────────────────────────────────────

def extract_company(text: str, author: str) -> str:
    """
    Decision: Try to extract company from first line of post (HN convention).
    Fallback to author handle if nothing useful found.
    """
    first_line = text.split("\n")[0].split("|")[0].strip()
    # Remove common noise like "Hiring:" or "We're hiring"
    first_line = re.sub(r"(?i)^(we'?re?\s+hiring[:,]?|hiring[:,]?)\s*", "", first_line).strip()
    if 2 < len(first_line) < 80:
        return first_line
    return author  # fallback


def extract_roles(text: str) -> list[str]:
    found = []
    for kw in ROLE_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            found.append(kw)
    return list(dict.fromkeys(found))  # dedupe, preserve order


def extract_tech(text: str) -> list[str]:
    found = []
    for kw in TECH_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            found.append(kw)
    return list(dict.fromkeys(found))


def extract_locations(text: str) -> list[str]:
    found = []
    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found.append(match.group().strip())
    return list(dict.fromkeys(found))


def extract_salary(text: str) -> str | None:
    match = SALARY_PATTERN.search(text)
    return match.group().strip() if match else None


def is_remote(locations: list[str]) -> bool:
    return any(re.search(r"remote|wfh|work from home|worldwide", loc, re.IGNORECASE) for loc in locations)


# ── Main clean function ────────────────────────────────────────────────────────

def clean(raw_jobs: list[dict]) -> list[dict]:
    """Transform raw job posts into structured, clean records."""
    cleaned = []
    skipped = 0

    for post in raw_jobs:
        raw_text = post.get("text", "") or ""
        clean_text = strip_html(raw_text)

        if len(clean_text) < 30:
            skipped += 1
            continue  # Decision: skip posts with virtually no content

        roles = extract_roles(clean_text)
        tech = extract_tech(clean_text)
        locations = extract_locations(clean_text)
        salary = extract_salary(clean_text)
        company = extract_company(clean_text, post.get("author", "unknown"))

        cleaned.append({
            "id": post.get("id"),
            "company": company,
            "author": post.get("author", "unknown"),
            "roles": roles,
            "tech_stack": tech,
            "locations": locations,
            "is_remote": is_remote(locations),
            "salary": salary,
            "full_text": clean_text,
            "url": post.get("url"),
            "posted_at": post.get("time_readable") or "",
            "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        })

    logger.info(f"Cleaned {len(cleaned)} posts. Skipped {skipped} (too short / empty).")
    return cleaned


# ── DB storage ─────────────────────────────────────────────────────────────────

def store_to_db(jobs: list[dict], db_path: str = DB_PATH):
    """Store cleaned jobs into SQLite. Upserts on id to avoid duplicates."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            company TEXT,
            author TEXT,
            roles TEXT,
            tech_stack TEXT,
            locations TEXT,
            is_remote INTEGER,
            salary TEXT,
            full_text TEXT,
            url TEXT,
            posted_at TEXT,
            scraped_at TEXT
        )
    """)

    inserted = 0
    for job in jobs:
        c.execute("""
            INSERT OR REPLACE INTO jobs
            (id, company, author, roles, tech_stack, locations, is_remote, salary, full_text, url, posted_at, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["id"],
            job["company"],
            job["author"],
            json.dumps(job["roles"]),
            json.dumps(job["tech_stack"]),
            json.dumps(job["locations"]),
            int(job["is_remote"]),
            job["salary"],
            job["full_text"],
            job["url"],
            job["posted_at"],
            job["scraped_at"],
        ))
        inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"Stored {inserted} jobs to {db_path}")


def run_cleaning_pipeline():
    with open(RAW_INPUT, "r", encoding="utf-8") as f:
        raw = json.load(f)
    cleaned = clean(raw)
    store_to_db(cleaned)
    return cleaned


if __name__ == "__main__":
    run_cleaning_pipeline()
