"""
scheduler.py
------------
Runs the full pipeline (scrape → clean → store) automatically on a schedule.
Uses APScheduler so no cron setup is needed — just run this file and it stays alive.

Schedule: Every 24 hours (HN Who's Hiring threads update monthly, but daily runs
ensure we catch edits and any new posts quickly).
"""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from scraper import scrape
from cleaner import clean, store_to_db
import json, os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RAW_OUTPUT = os.path.join("data", "raw_jobs.json")


def run_pipeline():
    logger.info("=== Pipeline run started ===")
    try:
        raw_jobs = scrape(max_posts=200)
        if not raw_jobs:
            logger.warning("No raw jobs scraped. Skipping cleaning step.")
            return
        cleaned = clean(raw_jobs)
        store_to_db(cleaned)
        logger.info(f"=== Pipeline complete: {len(cleaned)} jobs in DB ===")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    # Run once immediately on startup
    logger.info("Running pipeline immediately on startup...")
    run_pipeline()

    # Then schedule every 24 hours
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "interval", hours=24, id="pipeline")
    logger.info("Scheduler started. Pipeline will run every 24 hours.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
