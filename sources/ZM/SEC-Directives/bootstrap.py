#!/usr/bin/env python3
"""
ZM/SEC-Directives — Zambia Securities and Exchange Commission

Fetches capital markets directives, rules, guidelines, circulars, guidance
notes, and tribunal decisions from seczambia.org.zm.

Uses the WordPress REST API to discover posts by category, extracts PDF
download links from post content, then downloads and extracts full text.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.ZM.SEC-Directives")

BASE_URL = "https://www.seczambia.org.zm"
API_URL = f"{BASE_URL}/wp-json/wp/v2/posts"
DELAY = 2.0

# WordPress category IDs for regulatory documents
CATEGORIES = {
    24: "directive",
    20: "rule",
    21: "guideline",
    22: "tribunal_decision",
    23: "circular",
    25: "guidance_note",
}

# The Securities Act PDF is on a static page, not a post
SECURITIES_ACT_PDF = (
    f"{BASE_URL}/wp-content/uploads/2025/08/"
    "The-Securities-Act-No.-41-of-2016-Amended-by-Act-No.-21-of-2022.pdf"
)


def _decode_html(text: str) -> str:
    """Decode HTML entities in a string."""
    return html.unescape(text).strip()


def _make_id(post_id: int, slug: str) -> str:
    """Generate a stable ID from post ID and slug."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_")
    if len(clean) > 60:
        clean = clean[:60]
    return f"ZM_SEC_{post_id}_{clean}"


class SECScraper(BaseScraper):
    """Scraper for Zambia SEC regulatory documents."""

    def __init__(self):
        source_dir = Path(__file__).resolve().parent
        super().__init__(str(source_dir))
        self.http = HttpClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
            },
        )

    def _fetch_category_posts(self, cat_id: int, doc_type: str) -> List[Dict[str, Any]]:
        """Fetch all posts from a WordPress category using pagination."""
        posts = []
        page = 1
        while True:
            url = f"{API_URL}?categories={cat_id}&per_page=50&page={page}"
            logger.info("Fetching API: cat=%d page=%d", cat_id, page)
            resp = self.http.get(url, timeout=30)
            if resp.status_code != 200:
                if resp.status_code == 400:
                    break  # No more pages
                logger.warning("API HTTP %d for cat %d page %d", resp.status_code, cat_id, page)
                break

            data = resp.json()
            if not data:
                break

            for p in data:
                content_html = p.get("content", {}).get("rendered", "")
                # Extract PDF URLs from post content
                pdf_urls = re.findall(
                    r'href="([^"]*\.pdf[^"]*)"', content_html, re.I
                )
                # Clean up PDF URLs
                pdf_urls = [u.split("?")[0] for u in pdf_urls if BASE_URL in u or u.startswith("/")]
                pdf_urls = list(dict.fromkeys(pdf_urls))  # deduplicate preserving order

                if not pdf_urls:
                    # Some posts might have the text inline instead of a PDF
                    logger.info("No PDF found for post %d: %s", p["id"], p["title"]["rendered"][:50])

                posts.append({
                    "post_id": p["id"],
                    "title": _decode_html(p["title"]["rendered"]),
                    "date": p["date"][:10],  # YYYY-MM-DD
                    "slug": p["slug"],
                    "link": p["link"],
                    "doc_type": doc_type,
                    "pdf_urls": pdf_urls,
                    "content_html": content_html,
                })

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
            time.sleep(1)

        logger.info("Category %d (%s): %d posts", cat_id, doc_type, len(posts))
        return posts

    def _extract_inline_text(self, content_html: str) -> str:
        """Extract text from HTML content (for posts without PDFs)."""
        text = re.sub(r"<[^>]+>", " ", content_html)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _download_and_extract(self, pdf_url: str, doc_id: str) -> Optional[str]:
        """Download a PDF and extract text."""
        try:
            resp = self.http.get(pdf_url, timeout=60)
            if resp.status_code != 200:
                logger.warning("HTTP %d downloading %s", resp.status_code, pdf_url.split("/")[-1])
                return None
            pdf_bytes = resp.content
            if len(pdf_bytes) < 500:
                logger.warning("PDF too small (%d bytes): %s", len(pdf_bytes), pdf_url.split("/")[-1])
                return None
            text = extract_pdf_markdown("ZM/SEC-Directives", doc_id, pdf_bytes=pdf_bytes)
            return text
        except Exception as e:
            logger.warning("Failed to extract %s: %s", pdf_url.split("/")[-1], e)
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all SEC regulatory documents with full text."""
        # Collect all posts from all categories
        all_posts = []
        seen_ids = set()
        for cat_id, doc_type in CATEGORIES.items():
            posts = self._fetch_category_posts(cat_id, doc_type)
            for p in posts:
                if p["post_id"] not in seen_ids:
                    seen_ids.add(p["post_id"])
                    all_posts.append(p)
            time.sleep(DELAY)

        logger.info("Total unique posts: %d", len(all_posts))

        # Process each post
        for post in all_posts:
            doc_id = _make_id(post["post_id"], post["slug"])
            text = None

            # Try PDF extraction first
            for pdf_url in post["pdf_urls"]:
                logger.info("Downloading PDF: %s", pdf_url.split("/")[-1][:70])
                text = self._download_and_extract(pdf_url, doc_id)
                if text and len(text.strip()) >= 100:
                    break
                time.sleep(1)

            # Fall back to inline HTML content
            if not text or len(text.strip()) < 100:
                inline = self._extract_inline_text(post["content_html"])
                if len(inline) >= 200:
                    text = inline
                    logger.info("Using inline text for %s (%d chars)", post["title"][:40], len(text))

            if not text or len(text.strip()) < 100:
                logger.warning("Insufficient text for %s, skipping", post["title"][:50])
                continue

            yield {
                "_id": doc_id,
                "title": post["title"],
                "date": post["date"],
                "doc_type": post["doc_type"],
                "pdf_url": post["pdf_urls"][0] if post["pdf_urls"] else post["link"],
                "link": post["link"],
                "text": text,
            }
            time.sleep(DELAY)

        # Also fetch the Securities Act (static page PDF)
        logger.info("Fetching Securities Act PDF")
        act_id = "ZM_SEC_securities_act_41_2016_amended_21_2022"
        text = self._download_and_extract(SECURITIES_ACT_PDF, act_id)
        if text and len(text.strip()) >= 100:
            yield {
                "_id": act_id,
                "title": "The Securities Act, No. 41 of 2016 (Amended by Act No. 21 of 2022)",
                "date": "2022-01-01",
                "doc_type": "act",
                "pdf_url": SECURITIES_ACT_PDF,
                "link": f"{BASE_URL}/laws-and-regulations/securities-act-statutory-instruments/",
                "text": text,
            }

    def fetch_updates(self, since: str = "") -> Generator[dict, None, None]:
        """Fetch updates — re-fetch all for a small collection."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        return {
            "_id": raw["_id"],
            "_source": "ZM/SEC-Directives",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date"),
            "doc_type": raw.get("doc_type", ""),
            "url": raw.get("pdf_url") or raw.get("link", ""),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ZM/SEC-Directives bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Run full bootstrap")
    boot.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot.add_argument("--sample-size", type=int, default=15, help="Sample size")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    sub.add_parser("bootstrap-fast", help="Quick sample (alias for bootstrap --sample)")
    sub.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()
    scraper = SECScraper()

    if args.command == "test":
        resp = scraper.http.get(f"{API_URL}?categories=24&per_page=1", timeout=15)
        print(f"API test: HTTP {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"OK — {len(data)} post(s) returned from directives category")
        else:
            print("FAIL — API not accessible")
        return

    if args.command == "bootstrap-fast":
        stats = scraper.bootstrap(sample_mode=True, sample_size=15)
        print(json.dumps(stats, indent=2))
    elif args.command == "bootstrap":
        sample = args.sample and not args.full
        stats = scraper.bootstrap(sample_mode=sample, sample_size=args.sample_size)
        print(json.dumps(stats, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
