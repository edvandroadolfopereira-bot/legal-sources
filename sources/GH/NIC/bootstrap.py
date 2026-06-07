#!/usr/bin/env python3
"""
GH/NIC -- Ghana National Insurance Commission — Directives

Fetches regulatory directives, guidelines, and news from Ghana's NIC.

Strategy:
  - WordPress REST API "news" custom post type (~108 records, inline text)
  - WordPress REST API "pages" under Guidelines & Directives (parent=27)
    and Insurance Act (parent=9) — each page links to a PDF
  - PDFs are downloaded and text extracted via pdfplumber

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import re
import time
import logging
import html
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GH.NIC")

API_BASE = "https://nicgh.org/wp-json/wp/v2"
USER_AGENT = "LegalDataHunter/1.0 (research; https://github.com/ZachLaik/LegalDataHunter)"

MIN_TEXT_LENGTH = 150
GUIDELINES_PARENT_ID = 27
INSURANCE_ACT_PARENT_ID = 9


def strip_html(raw_html: str) -> str:
    """Remove HTML tags, decode entities, collapse whitespace."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", raw_html, flags=re.S | re.I)
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(p|div|h[1-6]|li|tr|td|th|blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_urls(html_content: str) -> list:
    """Extract PDF URLs from HTML content."""
    return re.findall(r'href=["\']([^"\'\s]+\.pdf)["\']', html_content, re.I)


def download_pdf_text(url: str, max_pages: int = 200) -> Optional[str]:
    """Download a PDF and extract text using pdfplumber."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()
        if len(resp.content) > 50_000_000:  # Skip PDFs > 50MB
            logger.warning(f"PDF too large ({len(resp.content)} bytes): {url}")
            return None
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name
        try:
            with pdfplumber.open(tmp_path) as pdf:
                pages_text = []
                for i, page in enumerate(pdf.pages[:max_pages]):
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                return "\n\n".join(pages_text) if pages_text else None
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"PDF extraction failed for {url}: {e}")
        return None


def wp_get(endpoint: str, params: dict = None, timeout: int = 30) -> requests.Response:
    """Make a GET request to the WordPress REST API."""
    url = f"{API_BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp


def paginate_wp(endpoint: str, params: dict = None, max_pages: int = 50) -> Generator[dict, None, None]:
    """Paginate through a WordPress REST API endpoint."""
    if params is None:
        params = {}
    params.setdefault("per_page", 100)
    page = 1

    while page <= max_pages:
        params["page"] = page
        try:
            resp = wp_get(endpoint, params=params)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                break
            raise

        data = resp.json()
        if not data:
            break

        for item in data:
            yield item

        total_pages = int(resp.headers.get("X-WP-TotalPages", max_pages))
        if page >= total_pages:
            break

        page += 1
        time.sleep(1.0)


class NICScraper(BaseScraper):
    """
    Scraper for GH/NIC — Ghana National Insurance Commission.
    Country: GH
    URL: https://nicgh.org/

    Data types: doctrine
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def _normalize_news_post(self, post: dict) -> Optional[dict]:
        """Normalize a WordPress news post into standard schema."""
        title = strip_html(post.get("title", {}).get("rendered", ""))
        content_html = post.get("content", {}).get("rendered", "")
        text = strip_html(content_html)

        if len(text) < MIN_TEXT_LENGTH:
            return None

        date_str = post.get("date", "")
        if date_str:
            date_str = date_str[:10]

        post_id = post.get("id", 0)
        link = post.get("link", f"https://nicgh.org/?p={post_id}")

        return {
            "_id": f"nic-gh-news-{post_id}",
            "_source": "GH/NIC",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_str or None,
            "url": link,
            "document_type": "news",
            "wp_id": post_id,
            "wp_modified": post.get("modified", "")[:10] if post.get("modified") else None,
        }

    def _normalize_guideline_page(self, page: dict) -> Optional[dict]:
        """Normalize a WordPress guideline/directive page with PDF extraction."""
        title = strip_html(page.get("title", {}).get("rendered", ""))
        content_html = page.get("content", {}).get("rendered", "")
        page_id = page.get("id", 0)
        link = page.get("link", f"https://nicgh.org/?p={page_id}")
        date_str = page.get("date", "")
        if date_str:
            date_str = date_str[:10]

        # Try to get text from PDF first
        pdf_urls = extract_pdf_urls(content_html)
        pdf_text = None
        pdf_url = None
        for url in pdf_urls:
            logger.info(f"Downloading PDF: {url}")
            pdf_text = download_pdf_text(url)
            if pdf_text and len(pdf_text) >= MIN_TEXT_LENGTH:
                pdf_url = url
                break
            time.sleep(1.0)

        # Fall back to inline text if no PDF
        inline_text = strip_html(content_html)
        text = pdf_text if pdf_text and len(pdf_text) >= MIN_TEXT_LENGTH else inline_text

        if len(text) < MIN_TEXT_LENGTH:
            logger.warning(f"Skipping page {page_id} '{title}': insufficient text ({len(text)} chars)")
            return None

        return {
            "_id": f"nic-gh-guideline-{page_id}",
            "_source": "GH/NIC",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_str or None,
            "url": link,
            "document_type": "guideline",
            "pdf_url": pdf_url,
            "wp_id": page_id,
            "wp_modified": page.get("modified", "")[:10] if page.get("modified") else None,
        }

    def normalize(self, raw: dict) -> dict:
        """Transform raw data into standard schema."""
        return raw

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all NIC documents: news posts + guideline/directive pages with PDFs."""
        yielded = 0

        # 1. Fetch guideline/directive pages (parent=27) with PDF extraction
        logger.info("Fetching NIC guideline/directive pages...")
        for page in paginate_wp("pages", params={"parent": GUIDELINES_PARENT_ID}):
            record = self._normalize_guideline_page(page)
            if record:
                yield record
                yielded += 1
                logger.info(f"Guideline [{yielded}]: {record['title'][:60]} ({len(record['text'])} chars)")

        # 2. Fetch Insurance Act page (parent=9)
        logger.info("Fetching Insurance Act page...")
        for page in paginate_wp("pages", params={"parent": INSURANCE_ACT_PARENT_ID}):
            record = self._normalize_guideline_page(page)
            if record:
                yield record
                yielded += 1
                logger.info(f"Act [{yielded}]: {record['title'][:60]} ({len(record['text'])} chars)")

        # 3. Fetch news posts
        logger.info("Fetching NIC news posts...")
        for post in paginate_wp("news"):
            record = self._normalize_news_post(post)
            if record:
                yield record
                yielded += 1
                if yielded % 25 == 0:
                    logger.info(f"Processed: {yielded} records")

        logger.info(f"fetch_all complete: {yielded} records")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Yield posts modified after 'since' date."""
        params = {"after": f"{since}T00:00:00", "orderby": "modified"}
        for post in paginate_wp("news", params=params):
            record = self._normalize_news_post(post)
            if record:
                yield record
        for page in paginate_wp("pages", params={"parent": GUIDELINES_PARENT_ID, "after": f"{since}T00:00:00", "orderby": "modified"}):
            record = self._normalize_guideline_page(page)
            if record:
                yield record


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="GH/NIC — Ghana National Insurance Commission"
    )
    subparsers = parser.add_subparsers(dest="command")

    bp = subparsers.add_parser("bootstrap", help="Full initial fetch")
    bp.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    bp.add_argument("--sample-size", type=int, default=15, help="Sample size")
    bp.add_argument("--full", action="store_true", help="Fetch all records")

    subparsers.add_parser("update", help="Incremental update")
    subparsers.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = NICScraper()

    if args.command == "test":
        logger.info("Testing NIC connectivity...")
        try:
            resp = wp_get("news", {"per_page": 1})
            data = resp.json()
            total = resp.headers.get("X-WP-Total", "?")
            logger.info(f"News endpoint: {total} records available")

            resp2 = wp_get("pages", {"parent": GUIDELINES_PARENT_ID, "per_page": 1})
            data2 = resp2.json()
            total2 = resp2.headers.get("X-WP-Total", "?")
            logger.info(f"Guidelines pages: {total2} records available")

            if data:
                record = scraper._normalize_news_post(data[0])
                if record:
                    logger.info(f"News sample: {record['title'][:80]}")
                    logger.info(f"Text: {len(record['text'])} chars")

            if data2:
                content_html = data2[0].get("content", {}).get("rendered", "")
                pdfs = extract_pdf_urls(content_html)
                logger.info(f"Guideline sample: {strip_html(data2[0]['title']['rendered'])[:80]}")
                logger.info(f"PDFs found: {len(pdfs)}")

            logger.info("Connectivity test passed!")
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            sys.exit(1)

    elif args.command == "bootstrap":
        stats = scraper.bootstrap(
            sample_mode=args.sample,
            sample_size=args.sample_size,
        )
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
