#!/usr/bin/env python3
"""
CK/CookIslandsLaws -- Cook Islands Consolidated Legislation Portal Fetcher

Fetches consolidated legislation from the official Cook Islands government
portal at cookislandslaws.gov.ck, powered by LexisNexis.

Strategy:
  - List all acts via REST API /retrieve_all_act (JSON)
  - For each act, get table of contents via /retrieve_toc/{ActName} (JSON)
  - Extract section IDs from the nested TOC structure
  - Fetch each section's HTML via /display_pages/{section_id}
  - Strip HTML tags, concatenate sections into full act text

Usage:
  python bootstrap.py bootstrap          # Fetch all documents
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from html import unescape

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.CK.CookIslandsLaws")

API_BASE = "https://cookislandslaws.gov.ck/api"


class CookIslandsLawsScraper(BaseScraper):
    """Scraper for CK/CookIslandsLaws -- Cook Islands consolidated legislation."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
        })

    def _request(self, url: str, timeout: int = 30, expect_json: bool = True):
        """HTTP GET with retry and rate limiting."""
        for attempt in range(3):
            try:
                time.sleep(1.0)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 500:
                    logger.warning("Server error (500) for %s, attempt %d", url, attempt + 1)
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                if expect_json:
                    return resp.json()
                return resp.text
            except requests.RequestException as e:
                logger.warning("Request error for %s: %s (attempt %d)", url, e, attempt + 1)
                if attempt < 2:
                    time.sleep(3)
        return None

    def _get_all_acts(self) -> List[Dict[str, Any]]:
        """Get list of all acts from the API."""
        data = self._request(f"{API_BASE}/retrieve_all_act")
        if not data:
            logger.error("Failed to retrieve act list")
            return []
        logger.info("Retrieved %d acts from API", len(data))
        return data

    def _extract_section_ids(self, toc_data) -> List[str]:
        """Recursively extract all section IDs from the nested TOC structure."""
        section_ids = []

        if isinstance(toc_data, dict):
            for key, value in toc_data.items():
                if key == "id":
                    section_ids.append(value)
                else:
                    section_ids.extend(self._extract_section_ids(value))
        elif isinstance(toc_data, list):
            for item in toc_data:
                section_ids.extend(self._extract_section_ids(item))

        return section_ids

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and clean text content."""
        if not html:
            return ""
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = unescape(text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()
        return text

    def _fetch_act_text(self, act_name: str) -> Optional[str]:
        """Fetch full text of an act by getting its TOC then all sections."""
        toc = self._request(f"{API_BASE}/retrieve_toc/{requests.utils.quote(act_name)}")
        if not toc:
            logger.warning("Failed to get TOC for: %s", act_name)
            return None

        section_ids = self._extract_section_ids(toc)
        if not section_ids:
            logger.warning("No section IDs found in TOC for: %s", act_name)
            return None

        logger.info("Act '%s' has %d sections", act_name, len(section_ids))

        all_text_parts = []
        for section_id in section_ids:
            html = self._request(
                f"{API_BASE}/display_pages/{requests.utils.quote(section_id)}",
                expect_json=False,
            )
            if html and not html.strip().startswith("<!doctype"):
                text = self._strip_html(html)
                if text:
                    all_text_parts.append(text)

        if not all_text_parts:
            return None

        return "\n\n".join(all_text_parts)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw act record into standard schema."""
        act_name = raw.get("ActName", "")
        legal_id = raw.get("LegalId", "")
        year = raw.get("Year", "")

        date_str = None
        if year:
            date_str = f"{year}-01-01"

        url = f"https://cookislandslaws.gov.ck/Consolidated-Laws?actName={requests.utils.quote(act_name)}"

        return {
            "_id": f"CK/CookIslandsLaws/{legal_id}",
            "_source": "CK/CookIslandsLaws",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": act_name,
            "text": raw.get("text", ""),
            "date": date_str,
            "url": url,
            "legal_id": legal_id,
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all Cook Islands consolidated legislation."""
        acts = self._get_all_acts()
        seen_legal_ids = set()

        for act in acts:
            legal_id = act.get("LegalId", "")
            act_name = act.get("ActName", "")

            if not legal_id or not act_name:
                continue

            if legal_id in seen_legal_ids:
                continue
            seen_legal_ids.add(legal_id)

            logger.info("Fetching act: %s (%s)", act_name, legal_id)
            text = self._fetch_act_text(act_name)
            if not text:
                logger.warning("No text retrieved for: %s", act_name)
                continue

            act["text"] = text
            yield self.normalize(act)

    def fetch_sample(self, count: int = 15) -> Generator[Dict[str, Any], None, None]:
        """Fetch a sample of acts for testing."""
        acts = self._get_all_acts()
        if not acts:
            return

        seen_legal_ids = set()
        yielded = 0

        for act in acts:
            if yielded >= count:
                break

            legal_id = act.get("LegalId", "")
            act_name = act.get("ActName", "")
            if not legal_id or not act_name:
                continue
            if legal_id in seen_legal_ids:
                continue
            seen_legal_ids.add(legal_id)

            logger.info("[Sample %d/%d] Fetching: %s", yielded + 1, count, act_name)
            text = self._fetch_act_text(act_name)
            if not text:
                logger.warning("Skipping %s (no text)", act_name)
                continue

            act["text"] = text
            yield self.normalize(act)
            yielded += 1

    def fetch_updates(self, since) -> Generator[Dict[str, Any], None, None]:
        """Fetch updates since a given date (not supported, yields all)."""
        yield from self.fetch_all()

    def test(self) -> bool:
        """Quick connectivity test."""
        data = self._request(f"{API_BASE}/retrieve_all_act")
        if data and len(data) > 0:
            logger.info("API connectivity OK: %d acts available", len(data))
            return True
        logger.error("API connectivity test FAILED")
        return False


def main():
    scraper = CookIslandsLawsScraper()
    args = sys.argv[1:]

    if not args or args[0] == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    if args[0] in ("bootstrap", "bootstrap-fast"):
        sample_mode = "--sample" in args
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        gen = scraper.fetch_sample(15) if sample_mode else scraper.fetch_all()

        for record in gen:
            count += 1
            text_len = len(record.get("text", ""))
            logger.info(
                "Record %d: %s (%d chars)",
                count, record["title"], text_len,
            )

            if sample_mode:
                fname = re.sub(r'[^\w\-.]', '_', record["_id"]) + ".json"
                out_path = sample_dir / fname
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)

        logger.info("Done. Total records: %d", count)
    else:
        print(f"Unknown command: {args[0]}")
        print("Usage: python bootstrap.py [bootstrap [--sample] | test]")
        sys.exit(1)


if __name__ == "__main__":
    main()
