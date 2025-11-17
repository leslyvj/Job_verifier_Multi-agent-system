"""Utility script to confirm network scraping works end-to-end.

Run it manually (not via pytest):
    python tests/manual_scrape_check.py <job_url>

It will:
1. Activate DEBUG logging so you can see each request in the console.
2. Invoke ``scrape_job`` to fetch the remote job posting.
3. Print the returned payload so you can inspect the scraped fields.

This performs a live HTTP request; only use against sources you are
permitted to scrape.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:  # ensure app package is importable when run directly
    sys.path.insert(0, str(ROOT_DIR))

from app.services import scrape_job
from app.utils.logger import configure_logging
from app.workflows import ParentOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a job posting via scrape_job")
    parser.add_argument("url", help="Job posting URL to scrape")
    args = parser.parse_args(argv)

    configure_logging(level=logging.DEBUG)
    logging.getLogger(__name__).info("Starting scrape for %s", args.url)

    scraped = scrape_job(args.url)
    print("\n=== scrape_job result ===")
    print(json.dumps(scraped, indent=2, ensure_ascii=False))
    print("========================\n")

    orchestrator = ParentOrchestrator()
    outcome = orchestrator.process_job(args.url)
    profile = (outcome.get("summary") or {}).get("structured_profile")

    print("=== structured_profile (LLM enhanced) ===")
    if profile:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    else:
        print("LLM output unavailable; check LLM_PROVIDER or logs for details.")
    print("========================================\n")

    return 0


if __name__ == "__main__":  # pragma: no cover - manual smoke tool
    raise SystemExit(main())
