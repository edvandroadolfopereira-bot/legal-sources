#!/usr/bin/env python3
"""
INTL/ConstituteProject -- World Constitutions (Comparative Constitutions Project)

Fetches full text of national constitutions from the Constitute Project API.

Strategy:
  - GET /service/constitutions to list all ~233 constitutions
  - GET /service/html?cons_id={id}&lang=en to fetch full HTML text
  - Strip HTML tags to produce clean plain text
  - ~233 constitutions covering ~200 countries

Usage:
  python bootstrap.py bootstrap          # Full initial pull (writes data/records.jsonl)
  python bootstrap.py bootstrap --sample # Fetch sample records to sample/
  python bootstrap.py bootstrap-fast     # Concurrent full pull (fleet alias)
  python bootstrap.py update             # Re-fetch (API has no date filter)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
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
    # Drop Constitute section markers like [[anchor]]
    text = re.sub(r'\[\[.*?\]\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
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
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
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

    def _fetch_constitution_html(self, cons_id: str) -> Optional[str]:
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

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield constitution metadata records (full text fetched in normalize)."""
        resp = self.session.get(f"{API_BASE}/constitutions", timeout=30)
        resp.raise_for_status()
        constitutions = resp.json()
        logger.info(f"Found {len(constitutions)} constitutions")

        # Filter to public, showable constitutions
        constitutions = [c for c in constitutions if c.get("public") and c.get("show")]
        logger.info(f"After filtering: {len(constitutions)} public constitutions")

        for meta in constitutions:
            yield meta

    def fetch_updates(self, since) -> Generator[dict, None, None]:
        """The API has no date filter; re-yield everything."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> Optional[dict]:
        """Fetch full text and normalize a constitution record."""
        cons_id = raw.get("id", "")
        if not cons_id:
            return None

        html_text = self._fetch_constitution_html(cons_id)
        text = strip_html(html_text) if html_text else ""
        if len(text) < 100:
            logger.warning(f"Insufficient text for {cons_id}: {len(text)} chars")
            return None

        year = raw.get("year_enacted") or raw.get("year_drafted")
        date_str = f"{year}-01-01" if year else None

        return {
            "_id": cons_id,
            "_source": self.SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title_long") or raw.get("title", ""),
            "text": text,
            "date": date_str,
            "url": f"{self.BASE_URL}/constitution/{cons_id}",
            "country": raw.get("country", ""),
            "country_id": raw.get("country_id", ""),
            "region": raw.get("region", ""),
            "in_force": raw.get("in_force", False),
            "word_length": raw.get("word_length"),
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    scraper = ConstituteProjectScraper()
    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test":
        sys.exit(0 if scraper.test() else 1)
    elif command == "bootstrap":
        scraper.bootstrap(sample_mode=sample_mode)
    elif command == "bootstrap-fast":
        if sample_mode:
            scraper.bootstrap(sample_mode=True)
        else:
            scraper.bootstrap_fast()
    elif command == "update":
        scraper.update()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
