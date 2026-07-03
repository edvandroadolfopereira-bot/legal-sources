#!/usr/bin/env python3
"""
INTL/IGAD-Legal -- IGAD Communiqués, Summit Decisions & Ministerial Declarations

Fetches legal instruments from the IGAD WordPress REST API:
  - Communiqués (category 52): ~115 summit/ministerial communiqués and decisions

Strategy:
  - Paginate through WP REST API (/wp-json/wp/v2/posts?categories=52)
  - Full rendered HTML content is returned; strip tags for clean text
  - Normalize to standard schema

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap --full     # Full fetch
  python bootstrap.py bootstrap-fast       # Alias for --full
"""

import re
import sys
import json
import time
import logging
import hashlib
from html import unescape
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.IGAD-Legal")

SOURCE_ID = "INTL/IGAD-Legal"
API_BASE = "https://igad.int/wp-json/wp/v2"

# Category ID for communiqués on the IGAD WordPress site
COMMUNIQUE_CATEGORY = 52


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities, preserving paragraph breaks."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class IGADLegalScraper(BaseScraper):
    """
    Scraper for INTL/IGAD-Legal.
    Country: INTL
    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "application/json",
        })

    def _fetch_wp_posts(self, category_id: int, per_page: int = 100) -> Generator[dict, None, None]:
        """Paginate through WP REST API posts for a given category."""
        page = 1
        while True:
            url = (
                f"{API_BASE}/posts"
                f"?categories={category_id}"
                f"&per_page={per_page}"
                f"&page={page}"
                f"&_fields=id,date,title,content,link,excerpt,modified"
            )
            logger.info(f"Fetching page {page}: {url}")
            try:
                resp = self.session.get(url, timeout=60)
            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                break

            if resp.status_code == 400:
                # WP returns 400 when page > total pages
                break
            resp.raise_for_status()

            posts = resp.json()
            if not posts:
                break

            for post in posts:
                yield post

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break

            page += 1
            time.sleep(1)

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all IGAD communiqués from the WordPress API."""
        logger.info("Fetching IGAD communiqués via WP REST API")
        count = 0
        for post in self._fetch_wp_posts(COMMUNIQUE_CATEGORY):
            post["_instrument_type"] = "communiqué"
            yield post
            count += 1
        logger.info(f"Total communiqués fetched: {count}")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield documents modified since the given datetime."""
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
        page = 1
        while True:
            url = (
                f"{API_BASE}/posts"
                f"?categories={COMMUNIQUE_CATEGORY}"
                f"&per_page=100"
                f"&page={page}"
                f"&modified_after={since_iso}"
                f"&_fields=id,date,title,content,link,excerpt,modified"
            )
            try:
                resp = self.session.get(url, timeout=60)
            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                break

            if resp.status_code == 400:
                break
            resp.raise_for_status()

            posts = resp.json()
            if not posts:
                break

            for post in posts:
                post["_instrument_type"] = "communiqué"
                yield post

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break

            page += 1
            time.sleep(1)

    def normalize(self, raw: dict) -> dict:
        """Transform a WP REST API post into standardized schema."""
        wp_id = raw.get("id")
        title_raw = raw.get("title", {}).get("rendered", "")
        title = unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()

        content_html = raw.get("content", {}).get("rendered", "")
        text = strip_html(content_html)

        if not text or len(text) < 50:
            logger.debug(f"Skipping post {wp_id}: insufficient text ({len(text)} chars)")
            return None

        date_str = raw.get("date", "")
        date_iso = None
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                date_iso = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_iso = None

        url = raw.get("link", f"https://igad.int/?p={wp_id}")
        instrument_type = raw.get("_instrument_type", "communiqué")

        doc_id = f"igad-{instrument_type}-{wp_id}"

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": url,
            "instrument_type": instrument_type,
            "wp_id": wp_id,
        }


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/IGAD-Legal scraper")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Bootstrap the data source")
    boot.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    sub.add_parser("bootstrap-fast", help="Alias for bootstrap --full")

    args = parser.parse_args()
    scraper = IGADLegalScraper()

    if args.command == "bootstrap-fast":
        stats = scraper.bootstrap(sample_mode=False)
    elif args.command == "bootstrap":
        if args.sample:
            stats = scraper.bootstrap(sample_mode=True, sample_size=15)
        else:
            stats = scraper.bootstrap(sample_mode=False)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
