# HireSignal — B2B Talent Intelligence Pipeline

> A fully automated data pipeline that scrapes, cleans, and surfaces real-time hiring signals from HackerNews — built for B2B sales, recruitment, and market intelligence use cases.

---

## The Problem Being Solved

Businesses — especially B2B SaaS companies, recruiting firms, and market researchers — need to know *who is hiring*, *for what*, and *with what technology stack* in real time. This is a strong commercial signal:

- A company hiring 5 ML engineers is likely evaluating AI tooling → sales opportunity
- A startup posting 10 roles signals rapid growth → VC/investor intelligence
- A company hiring Rust/Go engineers signals infrastructure investment → competitive intelligence

**HackerNews "Who is Hiring?"** is one of the most trusted, signal-rich, unsponsored job boards on the internet — posted monthly by thousands of tech companies. The data is public, structured in natural language, and updated continuously.

This pipeline collects, cleans, and delivers that data through a queryable API and dashboard.

---

## Architecture

```
┌────────────────┐     ┌────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  HN Firebase   │────▶│  scraper.py    │────▶│  cleaner.py  │────▶│  SQLite (jobs.db)│
│  Public API    │     │  (pagination + │     │  (NLP tags + │     │                  │
│                │     │   retry logic) │     │   normalise) │     └────────┬─────────┘
└────────────────┘     └────────────────┘     └──────────────┘              │
                                                                             ▼
                        ┌─────────────────────────────────────────────────────────────┐
                        │  app.py  — Flask API + Dashboard                            │
                        │  GET /api/jobs  ·  GET /api/stats  ·  POST /api/refresh     │
                        └─────────────────────────────────────────────────────────────┘
                                                ▲
                        ┌───────────────────────┘
                        │  scheduler.py  — APScheduler (runs pipeline every 24h)
                        └──────────────────────────────────────────────────────
```

---

## Features

| Phase | What it does |
|-------|-------------|
| **Scrape** | Fetches up to 200 job posts from the latest HN hiring thread via the official Firebase API. Handles pagination, retries (3x with backoff), missing fields, deleted/dead posts. |
| **Clean** | Strips HTML, extracts company name, roles, tech stack, location, salary, remote status using keyword matching + regex heuristics. Documents every decision in code. |
| **Store** | Upserts into SQLite — safe to re-run, no duplicates. |
| **Automate** | APScheduler runs the full pipeline every 24 hours with zero manual intervention. |
| **Serve** | Flask API with filtering by tech, role, remote, and free-text search. |
| **Dashboard** | Live UI with stats, bar charts, filterable job cards, expandable full text. |

---

## Quickstart — One Command

```bash
git clone https://github.com/YOUR_USERNAME/hiresignal.git
cd hiresignal
python run.py
```

That's it. `run.py` will:
1. Install all dependencies automatically
2. Scrape live job posts from HackerNews (~60–90 seconds)
3. Clean and store the data into SQLite
4. Launch the dashboard at **http://localhost:5000** (opens in browser automatically)

> **Requirements:** Python 3.9+ and pip. No API keys needed.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Port for the Flask server |

No API keys are required. This project uses the public HackerNews Firebase API (`https://hacker-news.firebaseio.com/v0`).

---

## Running Individual Steps (optional)

If you want to run each phase separately:

```bash
pip install -r requirements.txt
python scraper.py        # → data/raw_jobs.json
python cleaner.py        # → data/jobs.db
python app.py            # → http://localhost:5000
```

To run the pipeline on a 24-hour automated schedule:

```bash
python scheduler.py
```

---

## API Reference

### `GET /api/jobs`

Returns a list of cleaned job postings.

**Query params:**

| Param | Example | Description |
|-------|---------|-------------|
| `q` | `?q=fintech` | Free-text search in company name and post body |
| `tech` | `?tech=Python` | Filter by technology |
| `remote` | `?remote=true` | Remote roles only |
| `limit` | `?limit=25` | Max results (default 50, max 200) |

**Example response:**
```json
[
  {
    "id": 39876543,
    "company": "Acme Corp",
    "roles": ["Software Engineer", "Backend"],
    "tech_stack": ["Python", "PostgreSQL", "AWS"],
    "locations": ["Remote", "San Francisco"],
    "is_remote": true,
    "salary": "$150k - $200k",
    "url": "https://news.ycombinator.com/item?id=39876543",
    "posted_at": "2025-05-01 10:22"
  }
]
```

### `GET /api/stats`

Returns aggregate intelligence across all jobs.

```json
{
  "total_jobs": 187,
  "remote_count": 134,
  "remote_pct": 71.7,
  "top_technologies": [
    {"name": "Python", "count": 89},
    {"name": "TypeScript", "count": 67}
  ],
  "top_locations": [
    {"name": "Remote", "count": 134}
  ]
}
```

### `POST /api/refresh`

Triggers a full pipeline run in the background.

```bash
curl -X POST http://localhost:5000/api/refresh
```

---



## Data Cleaning Decisions

All decisions are documented inline in `cleaner.py`. Summary:

| Decision | Rationale |
|----------|-----------|
| Strip HTML tags | HN API returns text as escaped HTML; plain text is more useful for NLP |
| Extract company from first line | HN convention — posters lead with company name |
| Skip posts < 30 chars | No extractable signal; flagged in logs, not silently dropped |
| Use keyword matching for tech/roles | Fast, interpretable, no model dependency; sufficient for MVP |
| Upsert on `id` | Re-runs are idempotent; no duplicate rows |
| Keep all posts even with low signal | Auditability — nothing is silently deleted |

---

## Project Structure

```
hiresignal/
├── scraper.py          # Fetches raw data from HN API
├── cleaner.py          # Cleans, tags, and stores to SQLite
├── scheduler.py        # Runs pipeline automatically every 24h
├── app.py              # Flask API + dashboard UI
├── requirements.txt
├── run.py              # Single File to run the Scraper
├── .env.example
├── .gitignore
└── data/               # Created at runtime
    ├── raw_jobs.json   # Raw scraper output
    └── jobs.db         # Cleaned SQLite database
```

---

## Tech Stack

- **Python 3.11** — scraping, cleaning, API
- **Flask** — lightweight API server
- **SQLite** — zero-config relational store, suitable for this read-heavy use case
- **APScheduler** — in-process scheduler, no external dependencies
- **Requests** — HTTP with retry logic
- **Gunicorn** — production WSGI server

---