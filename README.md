# HireSignal — B2B Talent Intelligence Pipeline

> A fully automated data pipeline that scrapes, cleans, and surfaces real-time hiring signals from HackerNews — built for B2B sales, recruitment, and market intelligence use cases.

**Live demo:** [your-deployment-url.render.com](#deployment)

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

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/hiresignal.git
cd hiresignal
pip install -r requirements.txt
```

### 2. Run the pipeline (scrape + clean + store)

```bash
python scheduler.py
```

This runs the full pipeline immediately, then keeps running every 24 hours.
Wait ~2 minutes for the first run to complete (fetches ~200 posts).

To run just once without the scheduler:

```bash
python scraper.py        # → data/raw_jobs.json
python cleaner.py        # → data/jobs.db
```

### 3. Start the API server

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### 4. Environment variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Port for the Flask server |

> No API keys are required. This project uses the public HackerNews Firebase API (`https://hacker-news.firebaseio.com/v0`).

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

## Deployment

### Deploy to Render (free tier, recommended)

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repo
4. Set:
   - **Build command:** `pip install -r requirements.txt && python scheduler.py &`
   - **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Environment:** Python 3
5. Click **Deploy**

> Render's free tier spins down after inactivity. For a persistent worker + web combo, use the Background Worker + Web Service setup with the `Procfile`.

### One-command local run

```bash
pip install -r requirements.txt && python scheduler.py & sleep 90 && python app.py
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

## Bonus: AI Layer

A natural extension (not implemented in this MVP due to time constraints) would be to pass each job post through an LLM to:

1. **Classify company stage** (seed / series A / enterprise) based on post language
2. **Extract structured YAML** from free-text posts (company, role, comp, equity)
3. **Generate a "hiring intent score"** — how aggressively is this company hiring?

**Why this approach:** LLMs handle the ambiguity of natural language far better than regex for structured extraction. A single `claude-haiku` call per post (< $0.001) would dramatically improve field extraction quality.

**Trade-offs:**
- Cost: ~$0.20 per full run of 200 posts
- Latency: adds ~30s to pipeline run
- Dependency: requires API key and network

This is a clear Phase 2 improvement once the pipeline baseline is validated.

---

## Project Structure

```
hiresignal/
├── scraper.py          # Fetches raw data from HN API
├── cleaner.py          # Cleans, tags, and stores to SQLite
├── scheduler.py        # Runs pipeline automatically every 24h
├── app.py              # Flask API + dashboard UI
├── requirements.txt
├── Procfile            # For Render/Railway deployment
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

*Built as a data engineering internship assignment. Demonstrates end-to-end pipeline design: acquisition → transformation → storage → delivery → automation.*
