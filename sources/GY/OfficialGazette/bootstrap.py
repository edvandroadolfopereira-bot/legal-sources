#!/usr/bin/env python3
"""
GY/OfficialGazette -- Official Gazette of Guyana

Fetches gazette issues from officialgazette.gov.gy.

Strategy:
  - Paginate through /index.php/publications?start=N (20 items per page)
  - Parse HTML to extract gazette titles, dates, and PDF links
  - Download PDFs and extract text with pdfplumber
  - Each gazette issue = one record

Data:
  - ~2900 gazette issues (official, extraordinary, legal supplements)
  - Full text in English
  - License: Public Domain (Government Works)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import re
import io
import json
import logging
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from urllib.parse import urljoin

import pdfplumber
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GY.OfficialGazette")

BASE_URL = "https://officialgazette.gov.gy"
PUBLICATIONS_PATH = "/index.php/publications"
ITEMS_PER_PAGE = 20
MAX_PAGES = 200  # Safety cap

# Month name mapping for date parsing
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class OfficialGazetteScraper(BaseScraper):
    """
    Scraper for GY/OfficialGazette -- Official Gazette of Guyana.
    Country: GY
    URL: https://officialgazette.gov.gy

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "text/html,application/xhtml+xml",
        })
        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=60,
        )

    def _parse_date(self, title: str) -> Optional[str]:
        """Extract date from gazette title like 'Official Gazettes - 2nd May, 2026'."""
        # Pattern: day month, year
        m = re.search(
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(\w+),?\s+(\d{4})',
            title, re.IGNORECASE
        )
        if m:
            day = int(m.group(1))
            month_name = m.group(2).lower()
            year = int(m.group(3))
            month = MONTHS.get(month_name)
            if month:
                return f"{year}-{month:02d}-{day:02d}"
        return None

    def _classify_gazette(self, title: str) -> str:
        """Classify gazette type from title."""
        lower = title.lower()
        if "extraordinary" in lower or "extra" in lower:
            return "extraordinary"
        elif "legal supplement" in lower:
            return "legal_supplement"
        else:
            return "official"

    def _fetch_publications_page(self, start: int = 0) -> str:
        """Fetch one page of publications."""
        self.rate_limiter.wait()
        url = f"{PUBLICATIONS_PATH}?start={start}"
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def _parse_publications(self, html: str) -> List[Dict[str, str]]:
        """Parse gazette entries from publications page.

        HTML structure (Joomla blog layout):
          <div class="items-row ...">
            <h2 itemprop="name">TITLE</h2>
            ...
            <a href="/images/...pdf">PDF label</a>
            ...
            <div id="attachmentsList_com_content_article_ARTICLE_ID">
          </div>
        """
        entries = []

        # Split HTML into per-entry blocks using items-row dividers
        blocks = re.split(r'<div\s+class="items-row\b', html)

        for block in blocks[1:]:  # skip everything before first items-row
            # Extract title from <h2 itemprop="name">
            title_match = re.search(
                r'<h2\s+itemprop="name">\s*(.*?)\s*</h2>',
                block, re.DOTALL
            )
            if not title_match:
                continue
            title = re.sub(r'<[^>]+>', '', title_match.group(1))
            title = re.sub(r'\s+', ' ', title).strip()

            # Extract article ID from attachmentsList div
            id_match = re.search(
                r'attachmentsList_com_content_article_(\d+)', block
            )
            pub_id = id_match.group(1) if id_match else None

            # Extract PDF link(s)
            pdf_matches = re.findall(r'href="([^"]*\.pdf)"', block, re.IGNORECASE)
            if not pdf_matches:
                continue

            for raw_pdf in pdf_matches:
                # Fix backslash paths (Windows-style paths in Joomla)
                fixed_pdf = raw_pdf.replace("\\", "/")
                if not fixed_pdf.startswith("http"):
                    pdf_url = f"{BASE_URL}{fixed_pdf}"
                else:
                    pdf_url = fixed_pdf

                entries.append({
                    "pub_id": pub_id or hashlib.md5(
                        f"{title}-{fixed_pdf}".encode()
                    ).hexdigest()[:8],
                    "title": title,
                    "pdf_url": pdf_url,
                    "date": self._parse_date(title),
                    "gazette_type": self._classify_gazette(title),
                })

        return entries

    def _extract_text_from_pdf(self, pdf_url: str) -> Optional[str]:
        """Download PDF and extract text using pdfplumber."""
        try:
            self.rate_limiter.wait()
            logger.info(f"Downloading PDF: {pdf_url[-60:]}...")

            resp = self.session.get(pdf_url, timeout=180)
            resp.raise_for_status()

            content = resp.content
            size_mb = len(content) / (1024 * 1024)
            if size_mb > 50:
                logger.warning(f"PDF too large ({size_mb:.1f} MB), skipping")
                return None

            text_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    except Exception:
                        continue
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass

            full_text = "\n\n".join(text_parts)
            logger.info(f"Extracted {len(full_text)} chars from PDF ({size_mb:.1f} MB)")
            return full_text if full_text.strip() else None

        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all gazette documents with full text."""
        start = 0
        page_num = 0

        while page_num < MAX_PAGES:
            logger.info(f"Fetching publications page {page_num + 1} (start={start})...")
            try:
                html = self._fetch_publications_page(start)
            except Exception as e:
                logger.warning(f"Failed to fetch page at start={start}: {e}")
                break

            entries = self._parse_publications(html)
            if not entries:
                logger.info(f"No entries at start={start}, stopping")
                break

            for entry in entries:
                text = self._extract_text_from_pdf(entry["pdf_url"])
                if text:
                    entry["text"] = text
                    yield entry
                else:
                    logger.warning(f"No text for: {entry['title']}")

            start += ITEMS_PER_PAGE
            page_num += 1

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Fetch recent gazette issues."""
        # Only check first few pages for recent updates
        start = 0
        for page_num in range(5):
            logger.info(f"Checking updates page {page_num + 1}...")
            try:
                html = self._fetch_publications_page(start)
            except Exception:
                break

            entries = self._parse_publications(html)
            if not entries:
                break

            for entry in entries:
                if entry.get("date"):
                    try:
                        pub_date = datetime.strptime(entry["date"], "%Y-%m-%d")
                        if pub_date.date() < since.date():
                            return
                    except ValueError:
                        pass

                text = self._extract_text_from_pdf(entry["pdf_url"])
                if text:
                    entry["text"] = text
                    yield entry

            start += ITEMS_PER_PAGE

    def normalize(self, raw: dict) -> dict:
        """Transform raw gazette entry into standard schema."""
        text = raw.get("text", "")
        if not text or len(text.strip()) < 50:
            return None

        pub_id = raw.get("pub_id", "")
        title = raw.get("title", "")
        gazette_id = f"GY-OG-{pub_id}" if pub_id else hashlib.md5(title.encode()).hexdigest()[:12]

        return {
            "_id": f"GY/OfficialGazette/{gazette_id}",
            "_source": "GY/OfficialGazette",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "id": gazette_id,
            "gazette_id": gazette_id,
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "gazette_type": raw.get("gazette_type", "official"),
            "url": raw.get("pdf_url", ""),
            "country": "GY",
            "language": "en",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GY/OfficialGazette scraper")
    parser.add_argument("command", choices=["bootstrap", "update", "test"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = OfficialGazetteScraper()

    if args.command == "test":
        logger.info("Testing connectivity...")
        try:
            html = scraper._fetch_publications_page(0)
            entries = scraper._parse_publications(html)
            logger.info(f"Connection OK. Found {len(entries)} entries on page 1.")
            for e in entries[:3]:
                logger.info(f"  [{e['gazette_type']}] {e['title']} -> {e.get('date', 'no date')}")
            print("TEST PASSED")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            print("TEST FAILED")
            sys.exit(1)

    elif args.command == "bootstrap":
        sample_mode = args.sample or not args.full
        sample_size = 15 if sample_mode else 99999
        logger.info(f"Bootstrap (sample={sample_mode}, size={sample_size})")
        stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=sample_size)
        logger.info(f"Done: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update done: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
