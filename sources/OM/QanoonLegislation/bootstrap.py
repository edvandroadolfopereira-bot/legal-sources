#!/usr/bin/env python3
"""
OM/QanoonLegislation - Oman Royal Decrees and Legislation Fetcher

Fetches Omani legislation from qanoon.om via WordPress REST API.
~10,000+ documents: Royal Decrees, Ministerial Decisions, Legal Opinions.

Data access strategy:
  1. WP REST API for document listing + full text (/wp-json/wp/v2/posts)
  2. Category IDs: Royal Decrees (2), Ministerial Decisions (3), Legal Opinions (349)
  3. Full text in content.rendered field (HTML stripped to plain text)

License: Public Domain under Omani Copyright Law
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Generator, Optional

import logging
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.OM.QanoonLegislation")

BASE_URL = "https://qanoon.om"
API_URL = f"{BASE_URL}/wp-json/wp/v2/posts"
SAMPLE_DIR = Path(__file__).parent / "sample"
CHECKPOINT_FILE = Path(__file__).parent / "checkpoint.json"
SOURCE_ID = "OM/QanoonLegislation"

PER_PAGE = 100

# Main legislation categories on qanoon.om
CATEGORIES = {
    2: "royal_decree",       # مرسوم سلطاني (~4,888)
    3: "ministerial_decision",  # قرار وزاري (~4,468)
    349: "legal_opinion",    # فتاوى قانونية (~687)
}


def _strip_html(html_str: str) -> str:
    """Strip HTML tags and decode entities to plain text."""
    if not html_str:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html_str)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class QanoonLegislationScraper(BaseScraper):
    """Scraper for OM/QanoonLegislation — Omani legislation via qanoon.om."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json,text/html,*/*;q=0.8",
            "Accept-Language": "ar,en-US;q=0.7,en;q=0.3",
        })

    def _load_checkpoint(self) -> dict:
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        return {'current_category': None, 'last_page': 0, 'fetched_ids': []}

    def _save_checkpoint(self, checkpoint: dict):
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint, f, indent=2)

    def _fetch_api_page(self, category_id: int, page: int) -> tuple:
        """Fetch a page of posts from a category."""
        url = (
            f"{API_URL}?per_page={PER_PAGE}&page={page}"
            f"&categories={category_id}&orderby=date&order=asc"
        )
        logger.info(f"Fetching cat={category_id} page {page}")
        time.sleep(1)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("X-WP-Total", 0))
        total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
        return resp.json(), total, total_pages

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legislation documents with full text."""
        checkpoint = self._load_checkpoint()
        fetched_ids = set(checkpoint.get('fetched_ids', []))
        start_cat = checkpoint.get('current_category')
        start_page = checkpoint.get('last_page', 0) + 1

        started = start_cat is None
        for cat_id, doc_type in CATEGORIES.items():
            if not started:
                if cat_id == start_cat:
                    started = True
                else:
                    continue

            page = start_page if cat_id == start_cat else 1
            total_pages = None

            while True:
                try:
                    posts, total, tp = self._fetch_api_page(cat_id, page)
                except requests.RequestException as e:
                    logger.error(f"API request failed cat={cat_id} page={page}: {e}")
                    break

                if total_pages is None:
                    total_pages = tp
                    logger.info(f"Category {doc_type} (ID {cat_id}): {total} posts, {total_pages} pages")

                if not posts:
                    break

                for post in posts:
                    wp_id = post.get('id')
                    if wp_id in fetched_ids:
                        continue

                    slug = post.get('slug', '')
                    post_url = post.get('link', f"{BASE_URL}/p/{slug}/")
                    title = _strip_html(post.get('title', {}).get('rendered', slug))
                    content_html = post.get('content', {}).get('rendered', '')
                    full_text = _strip_html(content_html)
                    wp_date = post.get('date', '')

                    record = {
                        '_id': f"Qanoon-{wp_id}",
                        '_source': SOURCE_ID,
                        '_type': 'legislation',
                        '_fetched_at': datetime.now(timezone.utc).isoformat(),
                        'title': title,
                        'text': full_text,
                        'date': wp_date[:10] if wp_date else None,
                        'url': post_url,
                        'doc_type': doc_type,
                        'wp_id': wp_id,
                        'excerpt': _strip_html(post.get('excerpt', {}).get('rendered', '')),
                    }

                    yield record
                    fetched_ids.add(wp_id)

                checkpoint = {
                    'current_category': cat_id,
                    'last_page': page,
                    'fetched_ids': list(fetched_ids),
                }
                self._save_checkpoint(checkpoint)

                if page >= (total_pages or 1):
                    break
                page += 1

            # Reset page counter for next category
            start_page = 1

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Yield posts modified since a date."""
        for cat_id, doc_type in CATEGORIES.items():
            page = 1
            while True:
                try:
                    url = (
                        f"{API_URL}?per_page={PER_PAGE}&page={page}"
                        f"&categories={cat_id}&orderby=modified&order=desc"
                        f"&modified_after={since}"
                    )
                    time.sleep(1)
                    resp = self.session.get(url, timeout=30)
                    resp.raise_for_status()
                    posts = resp.json()
                    total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
                except requests.RequestException as e:
                    logger.error(f"API request failed: {e}")
                    break

                if not posts:
                    break

                for post in posts:
                    wp_id = post.get('id')
                    slug = post.get('slug', '')
                    post_url = post.get('link', f"{BASE_URL}/p/{slug}/")
                    title = _strip_html(post.get('title', {}).get('rendered', slug))
                    full_text = _strip_html(post.get('content', {}).get('rendered', ''))

                    yield {
                        '_id': f"Qanoon-{wp_id}",
                        '_source': SOURCE_ID,
                        '_type': 'legislation',
                        '_fetched_at': datetime.now(timezone.utc).isoformat(),
                        'title': title,
                        'text': full_text,
                        'date': post.get('date', '')[:10],
                        'url': post_url,
                        'doc_type': doc_type,
                    }

                if page >= total_pages:
                    break
                page += 1

    def normalize(self, raw: dict) -> dict:
        """Normalize a raw record to the standard schema."""
        return {
            '_id': raw.get('_id', ''),
            '_source': SOURCE_ID,
            '_type': 'legislation',
            '_fetched_at': raw.get('_fetched_at', datetime.now(timezone.utc).isoformat()),
            'title': raw.get('title', ''),
            'text': raw.get('text', ''),
            'date': raw.get('date'),
            'url': raw.get('url', ''),
            'doc_type': raw.get('doc_type', ''),
            'excerpt': raw.get('excerpt', ''),
        }


def bootstrap(sample: bool = False):
    """Bootstrap the OM/QanoonLegislation data source."""
    scraper = QanoonLegislationScraper()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    max_records = 15 if sample else float('inf')

    for record in scraper.fetch_all():
        normalized = scraper.normalize(record)

        if sample:
            safe_id = re.sub(r'[/\\:]', '_', normalized['_id'])
            out_file = SAMPLE_DIR / f"{safe_id}.json"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            text_len = len(normalized.get('text', '') or '')
            logger.info(
                f"[{count + 1}] {normalized['_id']} — "
                f"{text_len} chars text, type={normalized.get('doc_type')}, date={normalized.get('date')}"
            )

        count += 1
        if count >= max_records:
            break

    logger.info(f"Done. {count} records {'sampled' if sample else 'fetched'}.")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OM/QanoonLegislation bootstrap")
    parser.add_argument("action", choices=["bootstrap"], help="Action to perform")
    parser.add_argument("--sample", action="store_true", help="Fetch sample only (15 records)")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    if args.action == "bootstrap":
        bootstrap(sample=args.sample or not args.full)
