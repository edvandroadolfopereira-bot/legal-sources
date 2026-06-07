#!/usr/bin/env python3
"""
INTL/ConstituteProject -- World Constitutions (Comparative Constitutions Project)

Fetches full text of national constitutions from the Constitute Project API.

Strategy:
  - GET /service/constitutions to list all 232 constitutions
  - GET /service/html?cons_id={id}&lang=en to fetch full HTML text
  - Strip HTML tags to produce clean plain text
  - ~232 constitutions covering ~200 countries

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import time
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from html import unescape

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ConstituteProject")

API_BASE = "https://www.constituteproject.org/service"


def strip_html(html_text: str) -> str:
    """Strip HTML tags and clean up whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Clean up section markers
    text = re.sub(r'\[\[.*?\]\]', '', text)
    return text


class ConstituteProjectScraper(BaseScraper):
    """
    Scraper for INTL/ConstituteProject -- World Constitutions.
    Country: INTL
    URL: https://www.constituteproject.org/

    Data types: legislation
    Auth: none
    """

    SOURCE_ID = "INTL/ConstituteProject"
    BASE_URL = "https://www.constituteproject.org"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; +https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            resp = self.session.get(f"{API_BASE}/constitutions", timeout=15)
            data = resp.json()
            logger.info(f"API reachable: {len(data)} constitutions listed")
            return len(data) > 0
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            return False

    def fetch_constitution_list(self) -> list:
        """Fetch list of all constitutions."""
        resp = self.session.get(f"{API_BASE}/constitutions", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_constitution_html(self, cons_id: str) -> Optional[str]:
        """Fetch full HTML text for a constitution."""
        try:
            resp = self.session.get(
                f"{API_BASE}/html",
                params={"cons_id": cons_id, "lang": "en"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("html", "")
        except Exception as e:
            logger.warning(f"Failed to fetch HTML for {cons_id}: {e}")
            return None

    def normalize(self, raw_meta: dict, html_text: str) -> dict:
        """Normalize a constitution record."""
        cons_id = raw_meta.get("id", "")
        year = raw_meta.get("year_enacted") or raw_meta.get("year_drafted")
        date_str = f"{year}-01-01" if year else None

        text = strip_html(html_text) if html_text else ""

        return {
            "_id": cons_id,
            "_source": self.SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw_meta.get("title_long") or raw_meta.get("title", ""),
            "text": text,
            "date": date_str,
            "url": f"{self.BASE_URL}/constitution/{cons_id}",
            "country": raw_meta.get("country", ""),
            "country_id": raw_meta.get("country_id", ""),
            "region": raw_meta.get("region", ""),
            "in_force": raw_meta.get("in_force", False),
            "word_length": raw_meta.get("word_length"),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all constitutions with full text."""
        constitutions = self.fetch_constitution_list()
        logger.info(f"Found {len(constitutions)} constitutions")

        # Filter to public, showable constitutions
        constitutions = [c for c in constitutions if c.get("public") and c.get("show")]
        logger.info(f"After filtering: {len(constitutions)} public constitutions")

        if sample:
            constitutions = constitutions[:15]
            logger.info(f"Sample mode: fetching {len(constitutions)} constitutions")

        for i, meta in enumerate(constitutions):
            cons_id = meta.get("id", "")
            logger.info(f"[{i+1}/{len(constitutions)}] Fetching {cons_id}")

            html = self.fetch_constitution_html(cons_id)
            if not html:
                logger.warning(f"No HTML returned for {cons_id}, skipping")
                continue

            record = self.normalize(meta, html)

            if len(record.get("text", "")) < 100:
                logger.warning(f"Insufficient text for {cons_id}: {len(record.get('text', ''))} chars")
                continue

            yield record
            time.sleep(1)  # Rate limit

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Fetch all constitutions (API has no date filter)."""
        yield from self.fetch_all()


def main():
    scraper = ConstituteProjectScraper()
    source_dir = Path(__file__).parent
    sample_dir = source_dir / "sample"
    sample_dir.mkdir(exist_ok=True)

    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        ok = scraper.test()
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        count = 0
        for record in scraper.fetch_all(sample=sample):
            out_path = sample_dir / f"{record['_id'].replace('/', '_')}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
            text_len = len(record.get("text", ""))
            logger.info(f"  Saved {record['_id']} ({text_len:,} chars)")

        logger.info(f"Done: {count} constitutions saved to {sample_dir}")

    elif command == "update":
        count = 0
        for record in scraper.fetch_updates(""):
            out_path = sample_dir / f"{record['_id'].replace('/', '_')}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
        logger.info(f"Done: {count} constitutions updated")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
