#!/usr/bin/env python3
"""
CO/Fiscalia -- Fiscalia General de la Nacion (Colombia)

Fetches official communications and press releases from Colombia's Attorney
General's Office via the WordPress REST API. 67,000+ documents covering
organized crime, corruption, human rights, environmental crime, etc.

Source: https://www.fiscalia.gov.co/colombia/
API:    https://www.fiscalia.gov.co/colombia/wp-json/wp/v2/posts

Usage:
  python bootstrap.py bootstrap          # Full scan and fetch
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py update             # Fetch recent records (last 90 days)
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import html as htmlmod
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.CO.Fiscalia")

API_BASE = "https://www.fiscalia.gov.co/colombia/wp-json/wp/v2"
SOURCE_ID = "CO/Fiscalia"
SAMPLE_DIR = Path(__file__).parent / "sample"
CHECKPOINT_FILE = Path(__file__).parent / "checkpoint.json"

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "application/json",
}

DELAY = 1.5  # seconds between API requests
PER_PAGE = 100  # max per WP REST API


def strip_html(raw_html: str) -> str:
    """Strip HTML tags and clean up text."""
    text = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr|td|blockquote)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = htmlmod.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class FiscaliaScraper(BaseScraper):
    """Scraper for CO/Fiscalia -- Colombian prosecution service communications."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _load_checkpoint(self) -> dict:
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        return {"last_page": 0, "last_id": 0}

    def _save_checkpoint(self, checkpoint: dict):
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint, f, indent=2)

    def _fetch_page(self, page: int, per_page: int = PER_PAGE,
                    after: Optional[str] = None) -> list:
        """Fetch a page of posts from the WP REST API."""
        params = {
            "per_page": per_page,
            "page": page,
            "_fields": "id,date,title,content,link,categories",
            "orderby": "date",
            "order": "desc",
        }
        if after:
            params["after"] = after

        for attempt in range(3):
            try:
                time.sleep(DELAY)
                resp = self.session.get(f"{API_BASE}/posts", params=params, timeout=30)
                if resp.status_code == 400:
                    # past last page
                    return []
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning("Page %d attempt %d failed: %s", page, attempt + 1, e)
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        return []

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform a WP post into a normalized record."""
        title_raw = raw.get("title", {}).get("rendered", "")
        title = htmlmod.unescape(re.sub(r'<[^>]+>', '', title_raw)).strip()

        content_html = raw.get("content", {}).get("rendered", "")
        text = strip_html(content_html)

        if not text or len(text) < 50:
            return None

        post_id = raw.get("id", 0)
        date_str = raw.get("date", "")
        url = raw.get("link", "")

        # Parse date to ISO format
        date_iso = None
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                date_iso = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_iso = None

        return {
            "_id": f"co-fiscalia-{post_id}",
            "_source": SOURCE_ID,
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": url,
            "wp_post_id": post_id,
            "categories": raw.get("categories", []),
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all documents from the WP REST API."""
        checkpoint = self._load_checkpoint()
        start_page = checkpoint.get("last_page", 0) + 1

        page = start_page
        total_yielded = 0

        while True:
            logger.info("Fetching page %d...", page)
            posts = self._fetch_page(page)
            if not posts:
                logger.info("No more posts at page %d. Done.", page)
                break

            for post in posts:
                # Yield RAW posts — BaseScraper.bootstrap()/bootstrap_fast()
                # calls self.normalize() on each item itself. Yielding already
                # normalized records here would double-normalize (normalize()
                # expects raw WP shape, e.g. title.rendered) and drop every
                # record, persisting nothing. See "fetch_all must yield raw".
                yield post
                total_yielded += 1

            self._save_checkpoint({"last_page": page, "last_id": posts[-1]["id"]})

            if len(posts) < PER_PAGE:
                logger.info("Last page reached (got %d posts). Done.", len(posts))
                break

            page += 1

            if total_yielded % 1000 == 0:
                logger.info("Progress: %d records yielded so far.", total_yielded)

        logger.info("Completed: %d total records.", total_yielded)

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """Yield documents modified since a date.

        Accepts either an ISO string or a datetime (BaseScraper.update()
        passes a datetime); the WP REST `after` param needs an ISO8601 string.
        """
        if isinstance(since, datetime):
            since = since.strftime("%Y-%m-%dT%H:%M:%S")
        if not since:
            since_dt = datetime.now(timezone.utc) - timedelta(days=90)
            since = since_dt.strftime("%Y-%m-%dT00:00:00")

        page = 1
        total = 0

        while True:
            logger.info("Fetching updates page %d (after %s)...", page, since)
            posts = self._fetch_page(page, after=since)
            if not posts:
                break

            for post in posts:
                # Yield RAW — framework normalizes (see fetch_all).
                yield post
                total += 1

            if len(posts) < PER_PAGE:
                break
            page += 1

        logger.info("Updates complete: %d records since %s.", total, since)

    def fetch_sample(self, count: int = 15) -> list:
        """Fetch a small sample of records for validation."""
        logger.info("Fetching sample of %d records...", count)
        posts = self._fetch_page(1, per_page=count)
        records = []
        for post in posts:
            record = self.normalize(post)
            if record:
                records.append(record)
        return records

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        try:
            resp = self.session.get(f"{API_BASE}/posts",
                                    params={"per_page": 1, "_fields": "id"},
                                    timeout=15)
            total = resp.headers.get("X-WP-Total", "?")
            logger.info("Connection OK. Total posts: %s", total)
            return resp.status_code == 200
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False


def main():
    scraper = FiscaliaScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)

    if command in ("bootstrap", "bootstrap-fast"):
        sample_mode = "--sample" in sys.argv
        # Route through BaseScraper so records persist to data/records.jsonl
        # (the file the ingest pipeline reads) and samples are saved via the
        # framework. Previously the full path only counted records and wrote
        # nothing, so only the committed samples ever got ingested.
        stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=15)
        logger.info(
            "Bootstrap complete: fetched=%d new=%d updated=%d skipped=%d errors=%d",
            stats.get("records_fetched", 0),
            stats.get("records_new", 0),
            stats.get("records_updated", 0),
            stats.get("records_skipped", 0),
            stats.get("errors", 0),
        )

    elif command == "update":
        # BaseScraper.update() uses fetch_updates() under the hood and persists.
        stats = scraper.update()
        logger.info(
            "Update complete: new=%d updated=%d",
            stats.get("records_new", 0),
            stats.get("records_updated", 0),
        )

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
