"""
scraper.py
----------
Scrapes job postings from the HackerNews "Who's Hiring" thread via the official HN API.
This is a B2B talent intelligence use case — businesses can monitor hiring trends,
identify companies expanding in specific roles/locations, and use this as a lead signal.

Design decisions:
- Uses HN Firebase API (public, no auth, no scraping blocks)
- Handles pagination via chunked child item fetching
- Gracefully skips deleted/dead posts and missing fields
- Exports raw data to data/raw_jobs.json
"""

import requests
import json
import time
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"
DATA_DIR = "data"
RAW_OUTPUT = os.path.join(DATA_DIR, "raw_jobs.json")

os.makedirs(DATA_DIR, exist_ok=True)


def get_latest_hiring_thread() -> dict | None:
    """Find the most recent 'Ask HN: Who is hiring?' thread."""
    try:
        resp = requests.get(f"{HN_API}/user/whoishiring.json", timeout=10)
        resp.raise_for_status()
        user = resp.json()
        submitted = user.get("submitted", [])

        for item_id in submitted[:30]:  # Check last 30 submissions
            item_resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
            item_resp.raise_for_status()
            item = item_resp.json()
            if item and "Who is hiring?" in item.get("title", ""):
                logger.info(f"Found hiring thread: {item.get('title')} (id={item_id})")
                return item
    except requests.RequestException as e:
        logger.error(f"Failed to fetch hiring thread: {e}")
    return None


def fetch_item(item_id: int, retries: int = 3) -> dict | None:
    """Fetch a single HN item with retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt+1} failed for item {item_id}: {e}")
            time.sleep(1.5 * (attempt + 1))
    logger.error(f"Giving up on item {item_id} after {retries} attempts")
    return None


def parse_job_post(item: dict) -> dict | None:
    """
    Parse a raw HN comment into a structured job record.
    Returns None if the post is deleted, dead, or has no useful content.
    """
    if not item:
        return None
    if item.get("deleted") or item.get("dead"):
        return None

    text = item.get("text", "") or ""
    if not text.strip():
        return None

    return {
        "id": item.get("id"),
        "author": item.get("by", "unknown"),
        "text": text,
        "time": item.get("time"),
        "time_readable": datetime.utcfromtimestamp(item.get("time", 0)).strftime("%Y-%m-%d %H:%M")
        if item.get("time")
        else None,
        "score": item.get("score"),  # May be None for comments
        "url": f"https://news.ycombinator.com/item?id={item.get('id')}",
    }


def scrape(max_posts: int = 200) -> list[dict]:
    """
    Main scrape function. Fetches up to max_posts job postings
    from the latest HN Who's Hiring thread.
    """
    thread = get_latest_hiring_thread()
    if not thread:
        logger.error("Could not find a hiring thread. Aborting.")
        return []

    child_ids = thread.get("kids", [])
    logger.info(f"Thread has {len(child_ids)} top-level comments. Fetching up to {max_posts}.")

    raw_jobs = []
    for i, child_id in enumerate(child_ids[:max_posts]):
        item = fetch_item(child_id)
        parsed = parse_job_post(item)
        if parsed:
            raw_jobs.append(parsed)
        if i % 20 == 0 and i > 0:
            logger.info(f"Progress: {i}/{min(max_posts, len(child_ids))} fetched, {len(raw_jobs)} valid so far")
        time.sleep(0.05)  # Be polite

    logger.info(f"Scraping complete. {len(raw_jobs)} valid posts collected.")

    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(raw_jobs, f, indent=2, ensure_ascii=False)
    logger.info(f"Raw data saved to {RAW_OUTPUT}")

    return raw_jobs


if __name__ == "__main__":
    scrape()
