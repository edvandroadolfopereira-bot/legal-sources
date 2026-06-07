#!/usr/bin/env python3
"""
NP/NTA-Regulations -- Nepal Telecommunications Authority Regulations

Fetches directives, regulations, and guidelines from nta.gov.np:
  - Directives (~7), Regulations (~6), Guidelines (~9)
  - PDF full text extracted via common/pdf_extract
  - ~22 documents total

Strategy:
  1. Scrape listing tables from 3 category pages
  2. Extract PDF URLs and titles from table rows
  3. Download PDF and extract text with pdf_extract
  4. Prefer English PDFs when both English/Nepali exist
  5. 1-second delay between requests

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import urljoin, unquote, quote

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NP.NTA-Regulations")

BASE_URL = "https://www.nta.gov.np"
SAMPLE_DIR = Path(__file__).parent / "sample"
SOURCE_ID = "NP/NTA-Regulations"

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

CATEGORIES = [
    {"slug": "directives", "name": "Directives", "page_path": "/page/directives"},
    {"slug": "regulation", "name": "Regulations", "page_path": "/page/regulation"},
    {"slug": "guideline", "name": "Guidelines", "page_path": "/page/guideline"},
]

CRAWL_DELAY = 1


class NTARegulationsScraper(BaseScraper):
    """Scraper for NP/NTA-Regulations -- Nepal Telecommunications Authority."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False  # NTA cert sometimes fails verification

    def _get_page(self, url: str) -> Optional[str]:
        """Fetch a page with rate limiting."""
        time.sleep(CRAWL_DELAY)
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _download_pdf(self, pdf_url: str) -> Optional[bytes]:
        """Download a PDF file."""
        time.sleep(CRAWL_DELAY)
        try:
            # URL-encode non-ASCII characters in the path
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()
            if len(resp.content) < 100:
                logger.warning(f"PDF too small ({len(resp.content)} bytes): {pdf_url}")
                return None
            return resp.content
        except requests.RequestException as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {e}")
            return None

    def _extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF bytes using pdfplumber."""
        import tempfile
        try:
            import pdfplumber
        except ImportError:
            return extract_pdf_markdown(
                source=SOURCE_ID,
                source_id="",
                pdf_url="",
                table="legislation",
            )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            try:
                with pdfplumber.open(tmp.name) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            pages_text.append(text)
                    return "\n\n".join(pages_text) if pages_text else None
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")
                return None

    def _parse_table_rows(self, html: str, category_slug: str) -> list:
        """Parse document rows from an NTA category page HTML table."""
        items = []
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(tds) < 2:
                continue

            # Skip header rows
            if '<th' in row or 'S.N' in tds[0] or 'क्र.सं' in tds[0]:
                continue

            # Extract serial number
            sn = re.sub(r'<[^>]+>', '', tds[0]).strip()
            if not sn or not any(c.isdigit() for c in sn):
                continue

            # Extract title
            title = re.sub(r'<[^>]+>', '', tds[1]).strip()
            if not title:
                continue

            # Extract year
            year = ""
            if len(tds) > 2:
                year = re.sub(r'<[^>]+>', '', tds[2]).strip()

            # Extract PDF links
            pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', row)
            pdf_links = [p.strip() for p in pdf_links]

            if not pdf_links:
                continue

            # Prefer English PDF (non-np_ prefix, non-Nepali filename)
            en_pdf = None
            np_pdf = None
            for link in pdf_links:
                filename = link.split('/')[-1]
                if filename.startswith('np_'):
                    np_pdf = link
                elif all(ord(c) < 128 for c in filename.replace('%', 'X')):
                    en_pdf = link
                else:
                    np_pdf = link

            # Use English if available, otherwise Nepali
            primary_pdf = en_pdf or np_pdf or pdf_links[0]

            doc_id = hashlib.md5(primary_pdf.encode()).hexdigest()[:12]

            items.append({
                'doc_id': f"{category_slug}-{sn}-{doc_id}",
                'title': title,
                'year': year,
                'pdf_url': primary_pdf,
                'pdf_url_alt': np_pdf if en_pdf else en_pdf,
                'category': category_slug,
                'page_url': f"{BASE_URL}/page/{category_slug}",
            })

        return items

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        return {
            '_id': f"NP-NTA-{raw['doc_id']}",
            '_source': SOURCE_ID,
            '_type': 'legislation',
            '_fetched_at': datetime.now(timezone.utc).isoformat(),
            'title': raw['title'],
            'text': raw['text'],
            'date': raw.get('year', ''),
            'url': raw['pdf_url'],
            'pdf_url': raw.get('pdf_url', ''),
            'category': raw.get('category', ''),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Yield all documents from all categories."""
        sample_limit = 15 if sample else None
        total_yielded = 0

        for cat in CATEGORIES:
            if sample_limit and total_yielded >= sample_limit:
                break

            url = f"{BASE_URL}{cat['page_path']}"
            logger.info(f"\n=== Category: {cat['name']} ({url}) ===")

            html = self._get_page(url)
            if not html:
                logger.warning(f"Could not fetch category page: {url}")
                continue

            items = self._parse_table_rows(html, cat['slug'])
            logger.info(f"Found {len(items)} documents in {cat['name']}")

            for item in items:
                if sample_limit and total_yielded >= sample_limit:
                    break

                logger.info(f"  [{total_yielded + 1}] {item['title'][:60]}...")
                logger.info(f"      PDF: {unquote(item['pdf_url'])[:80]}")

                pdf_bytes = self._download_pdf(item['pdf_url'])
                if not pdf_bytes:
                    # Try alternate PDF if primary fails
                    if item.get('pdf_url_alt'):
                        logger.info(f"      Trying alternate PDF...")
                        pdf_bytes = self._download_pdf(item['pdf_url_alt'])
                    if not pdf_bytes:
                        logger.warning(f"      Skipping — could not download PDF")
                        continue

                text = self._extract_text_from_pdf_bytes(pdf_bytes)
                if not text or len(text) < 50:
                    logger.warning(f"      Skipping — insufficient text ({len(text) if text else 0} chars)")
                    continue

                logger.info(f"      Extracted {len(text)} chars")

                item['text'] = text
                record = self.normalize(item)

                if sample:
                    sample_path = SAMPLE_DIR / f"{record['_id']}.json"
                    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
                    with open(sample_path, 'w', encoding='utf-8') as f:
                        json.dump(record, f, indent=2, ensure_ascii=False)

                yield record
                total_yielded += 1

        logger.info(f"\nTotal documents yielded: {total_yielded}")

    def fetch_updates(self, since: str = None) -> Generator[dict, None, None]:
        """Fetch updates — for a small static collection, re-fetch all."""
        yield from self.fetch_all(sample=False)

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        try:
            resp = self.session.get(f"{BASE_URL}/page/directives", timeout=15)
            if resp.status_code == 200 and 'nta.gov.np' in resp.text.lower():
                logger.info("Connection test PASSED")
                return True
            logger.error(f"Connection test FAILED: status {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"Connection test FAILED: {e}")
            return False


def main():
    import argparse
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    parser = argparse.ArgumentParser(description="NP/NTA-Regulations scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Only fetch sample records")
    parser.add_argument("--full", action="store_true", help="Full fetch (default for bootstrap)")
    args = parser.parse_args()

    scraper = NTARegulationsScraper()

    if args.command == "test":
        success = scraper.test_connection()
        sys.exit(0 if success else 1)

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample = args.sample and not args.full
        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            logger.info(f"Record {count}: {record['_id']} — {record['title'][:50]}")
        logger.info(f"Bootstrap complete: {count} records")

    elif args.command == "update":
        count = 0
        for record in scraper.fetch_updates():
            count += 1
        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
