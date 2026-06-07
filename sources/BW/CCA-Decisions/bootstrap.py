#!/usr/bin/env python3
"""
BW/CCA-Decisions -- Botswana Competition and Consumer Authority — Merger Decisions

Fetches merger decisions from the CCA Drupal site.

Strategy:
  - Crawl paginated listing at /index.php/merger-decisions?page=N
  - Extract decision page slugs (/merger-decision-no-XX-YYYY-...)
  - Visit each decision page to extract the PDF link
  - Download PDF and extract full text via common.pdf_extract

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py test
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import unquote, urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BW.CCA-Decisions")

BASE_URL = "https://cca.co.bw"
LISTING_URL = "https://cca.co.bw/index.php/merger-decisions"


def _make_id(slug: str) -> str:
    """Create a stable document ID from the decision page slug."""
    # /merger-decision-no-18-2026-cfao-healthcare-and-medswana -> merger-decision-no-18-2026-...
    slug = slug.lstrip("/")
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)
    return slug[:150]


def _extract_title(slug: str) -> str:
    """Derive a human-readable title from the URL slug."""
    slug = slug.lstrip("/")
    title = slug.replace("-", " ").title()
    # Fix "No" casing
    title = re.sub(r"\bNo\b", "No", title)
    # Fix "Pty" etc
    title = re.sub(r"\bPty\b", "(Pty)", title)
    title = re.sub(r"\bLtd\b", "Ltd", title)
    return title


def _extract_year(slug: str) -> Optional[str]:
    """Extract year from slug like merger-decision-no-18-2026-..."""
    m = re.search(r"-no-\d+-(\d{4})-", slug)
    if m:
        return m.group(1)
    return None


class CCADecisionsScraper(BaseScraper):
    """Scraper for BW/CCA-Decisions -- Botswana CCA merger decisions."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
        })

    def _request(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(2)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 30s")
                    time.sleep(30)
                    continue
                if resp.status_code == 404:
                    logger.warning(f"404 for {url}")
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _get_decision_slugs(self, max_pages: int = 60) -> List[str]:
        """Crawl listing pages to get all decision page slugs."""
        all_slugs = []
        seen = set()

        for page in range(0, max_pages):
            url = f"{LISTING_URL}?page={page}"
            resp = self._request(url)
            if resp is None:
                logger.warning(f"Cannot fetch listing page {page}")
                break

            links = re.findall(r'(/merger-decision-no[^"\'\s>]+)', resp.text)
            unique = list(dict.fromkeys(links))
            new = [l for l in unique if l not in seen]
            seen.update(unique)
            all_slugs.extend(new)

            if not new and page > 0:
                logger.info(f"No new items on page {page}, stopping")
                break

            if page % 10 == 0:
                logger.info(f"Listing page {page}: {len(all_slugs)} decisions so far")

        logger.info(f"Found {len(all_slugs)} decision slugs total")
        return all_slugs

    def _get_pdf_url(self, slug: str) -> Optional[str]:
        """Visit a decision page and extract the PDF URL."""
        url = f"{BASE_URL}{slug}"
        resp = self._request(url)
        if resp is None:
            return None

        # Look for PDF in /sites/default/files/
        pdfs = re.findall(r'href="([^"]*sites/default/files[^"]*\.pdf)"', resp.text)
        if pdfs:
            return urljoin(url, pdfs[0])

        # Fallback: any PDF link
        pdfs = re.findall(r'href="([^"]*\.pdf)"', resp.text)
        if pdfs:
            return urljoin(url, pdfs[0])

        return None

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "BW/CCA-Decisions",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", None),
            "url": raw.get("url", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        # For sample mode, only crawl first few listing pages
        max_pages = 3 if max_records and max_records <= 20 else 60
        slugs = self._get_decision_slugs(max_pages=max_pages)

        if not slugs:
            logger.error("No decision slugs found")
            return

        count = 0
        for slug in slugs:
            if max_records and count >= max_records:
                return

            doc_id = _make_id(slug)
            title = _extract_title(slug)
            year = _extract_year(slug)

            logger.info(f"Processing: {title}")

            pdf_url = self._get_pdf_url(slug)
            if not pdf_url:
                logger.warning(f"No PDF found for {slug}")
                continue

            text = extract_pdf_markdown(
                source="BW/CCA-Decisions",
                source_id=doc_id,
                pdf_url=pdf_url,
                table="doctrine",
            )

            if not text or len(text) < 100:
                logger.warning(f"Insufficient text ({len(text or '')} chars): {title}")
                continue

            # Try to extract a better title from the PDF text
            pdf_title = None
            first_lines = text[:500].strip()
            m = re.match(r"(MERGER DECISION NO[^\n]+)", first_lines)
            if m:
                pdf_title = m.group(1).strip()

            date = f"{year}-01-01" if year else None

            raw = {
                "doc_id": doc_id,
                "title": pdf_title or title,
                "text": text,
                "date": date,
                "url": f"{BASE_URL}{slug}",
            }
            count += 1
            yield raw

        logger.info(f"Completed: {count} decisions fetched")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def test(self) -> bool:
        slugs = self._get_decision_slugs(max_pages=1)
        if not slugs:
            logger.error("Cannot fetch decision listing")
            return False

        logger.info(f"Listing OK: {len(slugs)} decisions on first page")

        slug = slugs[0]
        pdf_url = self._get_pdf_url(slug)
        if not pdf_url:
            logger.error(f"Cannot find PDF for {slug}")
            return False

        logger.info(f"Testing PDF: {pdf_url}")
        text = extract_pdf_markdown(
            source="BW/CCA-Decisions",
            source_id="test",
            pdf_url=pdf_url,
            table="doctrine",
            force=True,
        )
        if text:
            logger.info(f"PDF extraction OK: {len(text)} chars")
        else:
            logger.warning("PDF extraction returned no text")

        return True


def main():
    parser = argparse.ArgumentParser(description="BW/CCA-Decisions data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = CCADecisionsScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.bootstrap(sample_mode=args.sample, sample_size=15)
    elif args.command == "update":
        scraper.bootstrap(sample_mode=False)


if __name__ == "__main__":
    main()
