#!/usr/bin/env python3
"""
BA/BihKonk -- Bosnia and Herzegovina Competition Council Decision Fetcher

Fetches competition decisions from the Competition Council of BiH
(Konkurencijsko vijeće BiH) using the WordPress REST API.

Strategy:
  - Bootstrap: Paginate through WP REST API posts filtered by decision
    categories (concentrations, prohibited agreements, abuse of dominance,
    other). Extract PDF URLs from post content, download PDFs, extract text.
  - Update: Uses modified_after filter for incremental updates.
  - Sample: Fetches 15 records with full text for validation.

API: WordPress REST API (wp-json/wp/v2/)
Website: https://bihkonk.gov.ba

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py bootstrap-fast     # Full pull (same as bootstrap)
  python bootstrap.py update             # Incremental update (last week)
  python bootstrap.py test-api           # Quick API connectivity test
"""

import sys
import json
import logging
import time
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Generator
from html import unescape

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BA.BihKonk")

API_BASE = "https://bihkonk.gov.ba/wp-json/wp/v2"

# Bosnian-language decision categories (have the most content)
DECISION_CATEGORIES = {
    506: "concentrations",
    564: "prohibited_agreements",
    578: "abuse_of_dominance",
    536: "other",
}

# PDF URL extraction pattern from WordPress pdfemb viewer or direct links
PDF_URL_PATTERN = re.compile(
    r'href=["\']([^"\']*\.pdf)["\']', re.IGNORECASE
)


class BihKonkScraper(BaseScraper):
    """
    Scraper for BA/BihKonk — Competition Council of Bosnia and Herzegovina.

    Data types: doctrine
    Auth: none (public WordPress REST API + PDFs)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.client = HttpClient(
            base_url=API_BASE,
            headers={"User-Agent": "LegalDataHunter/1.0 (Open Data Research)"},
            timeout=60,
        )

        self.pdf_client = HttpClient(
            headers={"User-Agent": "LegalDataHunter/1.0 (Open Data Research)"},
            timeout=120,
        )

    def _paginate_posts(
        self,
        category_id: int,
        extra_params: dict = None,
        max_pages: int = None,
    ):
        """Paginate through WordPress posts for a given category."""
        page = 1
        total_pages = None
        per_page = 100

        while True:
            if max_pages and page > max_pages:
                return

            params = {
                "per_page": per_page,
                "page": page,
                "categories": category_id,
                "_fields": "id,date,modified,slug,title,content,link,categories",
            }
            if extra_params:
                params.update(extra_params)

            self.rate_limiter.wait()

            try:
                resp = self.client.get("/posts", params=params)
                resp.raise_for_status()
                data = resp.json()

                if total_pages is None:
                    total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
                    total_records = int(resp.headers.get("X-WP-Total", 0))
                    cat_name = DECISION_CATEGORIES.get(category_id, str(category_id))
                    logger.info(
                        f"Category {cat_name} ({category_id}): "
                        f"{total_records} records, {total_pages} pages"
                    )

            except Exception as e:
                logger.error(f"API error on category {category_id} page {page}: {e}")
                time.sleep(5)
                try:
                    resp = self.client.get("/posts", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e2:
                    logger.error(f"Retry failed: {e2}")
                    return

            if not data:
                return

            for post in data:
                post["_category_id"] = category_id
                yield post

            if page >= (total_pages or 1):
                return

            page += 1

    def _extract_pdf_url(self, content_html: str) -> str:
        """Extract the first PDF URL from WordPress post content HTML."""
        if not content_html:
            return ""
        matches = PDF_URL_PATTERN.findall(content_html)
        return matches[0] if matches else ""

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download PDF and extract text."""
        if not pdf_url:
            return ""
        return extract_pdf_markdown(
            source="BA/BihKonk",
            source_id="",
            pdf_url=pdf_url,
            table="doctrine",
        ) or ""

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all competition decisions across all categories."""
        for cat_id, cat_name in DECISION_CATEGORIES.items():
            logger.info(f"Fetching category: {cat_name} ({cat_id})")
            for post in self._paginate_posts(cat_id):
                yield post

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield records modified since the given date."""
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        extra_params = {"modified_after": since_str}

        for cat_id, cat_name in DECISION_CATEGORIES.items():
            logger.info(f"Fetching updates for {cat_name} since {since_str}")
            for post in self._paginate_posts(cat_id, extra_params=extra_params):
                yield post

    def normalize(self, raw: dict) -> dict:
        """Transform raw WordPress post into standard schema."""
        post_id = raw.get("id", "")
        title = self._clean_html(
            raw.get("title", {}).get("rendered", "")
        )
        date_str = raw.get("date", "")
        content_html = raw.get("content", {}).get("rendered", "")
        link = raw.get("link", "")
        category_id = raw.get("_category_id", 0)
        category_name = DECISION_CATEGORIES.get(category_id, "unknown")

        # Extract PDF URL from content
        pdf_url = self._extract_pdf_url(content_html)

        # Try PDF text extraction first
        text = ""
        if pdf_url:
            text = self._extract_pdf_text(pdf_url)

        # Fall back to inline HTML content if no PDF or PDF extraction failed
        if not text:
            text = self._clean_html(content_html)

        # Parse date
        date_iso = None
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_iso = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_iso = date_str[:10] if len(date_str) >= 10 else None

        return {
            "_id": f"BA-BihKonk-{post_id}",
            "_source": "BA/BihKonk",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "id": str(post_id),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": link,
            "pdf_url": pdf_url,
            "category": category_name,
        }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="BA/BihKonk bootstrapper")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Full bootstrap")
    boot.add_argument("--sample", action="store_true", help="Fetch sample only")

    fast = sub.add_parser("bootstrap-fast", help="Full bootstrap (alias)")
    fast.add_argument("--sample", action="store_true", help="Fetch sample only")

    upd = sub.add_parser("update", help="Incremental update")
    sub.add_parser("test-api", help="Test API connectivity")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = BihKonkScraper()

    if args.command == "test-api":
        logger.info("Testing WordPress REST API connectivity...")
        try:
            resp = scraper.client.get("/posts", params={"per_page": 1, "categories": 506})
            resp.raise_for_status()
            data = resp.json()
            total = resp.headers.get("X-WP-Total", "?")
            logger.info(f"API OK — {total} posts in concentrations category")
            logger.info(f"Sample title: {data[0]['title']['rendered'][:80]}")
        except Exception as e:
            logger.error(f"API test failed: {e}")
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = args.sample
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if sample_mode else None
        empty_text = 0

        for raw in scraper.fetch_all():
            record = scraper.normalize(raw)

            if not record.get("text"):
                empty_text += 1
                logger.warning(f"Empty text for {record['_id']}: {record.get('title', '')[:60]}")

            if sample_mode:
                out_path = sample_dir / f"{record['_id'].replace('/', '_')}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)

            count += 1
            if count % 10 == 0:
                logger.info(f"  Processed {count} records...")

            if max_records and count >= max_records:
                logger.info(f"Sample mode: reached {max_records} records")
                break

        logger.info(f"Done: {count} records, {empty_text} with empty text")
        if empty_text > 0:
            logger.warning(f"{empty_text}/{count} records have no full text")

    elif args.command == "update":
        since = datetime.now(timezone.utc) - timedelta(days=7)
        logger.info(f"Fetching updates since {since.isoformat()}")

        count = 0
        for raw in scraper.fetch_updates(since):
            record = scraper.normalize(raw)
            count += 1
            logger.info(f"  Updated: {record.get('title', '')[:60]}")

        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
