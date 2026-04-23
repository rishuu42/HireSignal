#!/usr/bin/env python3
"""
run.py
------
One-command setup and launch for HireSignal.
Usage: python run.py

This script will:
1. Install all dependencies
2. Run the scraper + cleaner pipeline
3. Start the Flask server at http://localhost:5000
"""

import subprocess
import sys
import os
import time
import webbrowser

def run(cmd, description):
    print(f"\n{'='*50}")
    print(f"  {description}")
    print(f"{'='*50}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n❌ Failed at: {description}")
        print(f"   Command was: {cmd}")
        sys.exit(1)
    print(f"✅ Done: {description}")

def main():
    print("""
╔══════════════════════════════════════╗
║        HireSignal Setup & Run        ║
║   B2B Talent Intelligence Pipeline  ║
╚══════════════════════════════════════╝
    """)

    # Step 1: Install dependencies
    run(
        f"{sys.executable} -m pip install -r requirements.txt --quiet",
        "Installing dependencies"
    )

    # Step 2: Create data directory
    os.makedirs("data", exist_ok=True)

    # Step 3: Run scraper
    run(
        f"{sys.executable} scraper.py",
        "Scraping HN jobs (this takes ~60-90 seconds)"
    )

    # Step 4: Run cleaner
    run(
        f"{sys.executable} cleaner.py",
        "Cleaning and storing data to SQLite"
    )

    # Step 5: Launch server
    print(f"\n{'='*50}")
    print("  Starting Flask server...")
    print(f"{'='*50}")
    print("\n🚀 HireSignal is running at: http://localhost:5000")
    print("   Press Ctrl+C to stop.\n")

    # Open browser after a short delay
    time.sleep(1)
    try:
        webbrowser.open("http://localhost:5000")
    except Exception:
        pass

    # Start Flask (blocking)
    subprocess.run(f"{sys.executable} app.py", shell=True)


if __name__ == "__main__":
    main()
