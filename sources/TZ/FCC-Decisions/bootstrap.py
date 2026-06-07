#!/usr/bin/env python3
"""
TZ/FCC-Decisions — Tanzania Fair Competition Commission Decisions

Fetches competition decisions (merger approvals, complaint rulings, provisional
findings) from the FCC's public REST API.

API base: https://www.fcc.go.tz/content/v1/
Endpoint: /publications/published-publications/list?page=N  (10 items/page)

Usage:
  python bootstrap.py bootstrap           # Full initial pull
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py test-api            # Quick connectivity test
"""

import sys
import json
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.TZ.FCC-Decisions")

SOURCE_ID = "TZ/FCC-Decisions"
API_BASE = "https://www.fcc.go.tz/content/v1"
LIST_ENDPOINT = f"{API_BASE}/publications/published-publications/list"
SOURCE_URL = "https://www.fcc.go.tz/decision"

# Categories to treat as case_law (by English name)
CASE_LAW_CATEGORIES = {"Decisions", "Provisional Findings"}


def _make_id(pub: dict) -> str:
    """Generate stable ID from publication ID."""
    pub_id = pub.get("publicationId", "")
    return f"TZ_FCC_{pub_id}" if pub_id else hashlib.md5(
        json.dumps(pub.get("name", {}), sort_keys=True).encode()
    ).hexdigest()


def _extract_text(pub: dict) -> str:
    """Extract text content from a publication record."""
    desc = pub.get("description", {})
    text_en = desc.get("en", "") if isinstance(desc, dict) else str(desc)
    return text_en.strip()


def _extract_category(pub: dict) -> str:
    """Get the English category name."""
    cat = pub.get("category", {})
    if isinstance(cat, dict):
        return cat.get("name", {}).get("en", "Unknown")
    return "Unknown"


def normalize(pub: dict) -> dict:
    """Transform a raw FCC publication into standard schema."""
    name = pub.get("name", {})
    title_en = name.get("en", "") if isinstance(name, dict) else str(name)
    title_sw = name.get("sw", "") if isinstance(name, dict) else ""

    text = _extract_text(pub)
    category = _extract_category(pub)

    issue_date = pub.get("issueDate")
    if issue_date and isinstance(issue_date, str):
        # Parse ISO date, keep just the date part
        try:
            issue_date = issue_date[:10]
        except Exception:
            pass

    attachment = pub.get("attachment", {})
    attachment_url = None
    if attachment and isinstance(attachment, dict):
        attachment_url = attachment.get("url")

    return {
        "_id": _make_id(pub),
        "_source": SOURCE_ID,
        "_type": "case_law" if category in CASE_LAW_CATEGORIES else "doctrine",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title_en,
        "title_sw": title_sw,
        "text": text,
        "date": issue_date,
        "url": SOURCE_URL,
        "category": category,
        "publication_id": pub.get("publicationId", ""),
        "attachment_url": attachment_url,
    }


def fetch_all_publications(http: HttpClient) -> Generator[dict, None, None]:
    """Paginate through all published publications."""
    page = 1
    while True:
        logger.info(f"Fetching page {page} ...")
        resp = http.get(LIST_ENDPOINT, params={"page": page})
        resp.raise_for_status()
        data = resp.json()

        pubs = data.get("publications", [])
        if not pubs:
            break

        for pub in pubs:
            yield pub

        pagination = data.get("pagination", {})
        total_pages = pagination.get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(1)


class FCCDecisionsScraper(BaseScraper):
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        super().__init__(source_id=SOURCE_ID)
        self.http = HttpClient(
            headers={"Accept": "application/json"},
            verify=False,
        )

    def fetch_all(self) -> Generator[dict, None, None]:
        count = 0
        for pub in fetch_all_publications(self.http):
            rec = normalize(pub)
            if rec["text"]:
                yield rec
                count += 1
            else:
                logger.warning(f"Skipping record with empty text: {rec['title'][:60]}")
        logger.info(f"Fetched {count} records total")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Fetch all and filter by date — API has no date filter."""
        for rec in self.fetch_all():
            if rec.get("_fetched_at", "") >= since:
                yield rec


def test_api():
    """Quick connectivity test."""
    http = HttpClient(headers={"Accept": "application/json"}, verify=False)
    resp = http.get(LIST_ENDPOINT, params={"page": 1})
    resp.raise_for_status()
    data = resp.json()
    pubs = data.get("publications", [])
    pagination = data.get("pagination", {})
    print(f"OK — {len(pubs)} publications on page 1, "
          f"total: {pagination.get('totalItems', '?')}")
    if pubs:
        first = pubs[0]
        name = first.get("name", {}).get("en", "N/A")
        print(f"First: {name[:80]}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TZ/FCC-Decisions bootstrap")
    parser.add_argument("command", choices=["bootstrap", "test-api"])
    parser.add_argument("--sample", action="store_true",
                        help="Save sample records for validation")
    args = parser.parse_args()

    if args.command == "test-api":
        test_api()
        return

    scraper = FCCDecisionsScraper()
    sample_dir = Path(__file__).parent / "sample"

    records = list(scraper.fetch_all())
    logger.info(f"Total records with text: {len(records)}")

    if args.sample:
        sample_dir.mkdir(exist_ok=True)
        for rec in records:
            safe_id = rec["_id"].replace("/", "_")
            path = sample_dir / f"{safe_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved sample: {path.name}")
        logger.info(f"Saved {len(records)} samples to {sample_dir}")
    else:
        for rec in records:
            print(json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
