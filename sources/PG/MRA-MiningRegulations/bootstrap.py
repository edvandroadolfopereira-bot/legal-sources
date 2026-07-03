#!/usr/bin/env python3
"""
PG/MRA-MiningRegulations -- Papua New Guinea Mining Regulations

Fetches mining legislation and policies from mra.gov.pg:
  - Mining Act 1992, Mining (Safety) Act 1977, MRA Act 2005
  - Environment Act 2000, Gold Export reqs, Alluvial/Geothermal policies
  - PDF full text extracted via pdfplumber
  - ~7 documents total

Strategy:
  1. Scrape the regulations page for PDF download links
  2. Derive title from PDF filename
  3. Download and extract text with pdfplumber
  4. 1-second delay between requests

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records
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
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import unquote

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PG.MRA-MiningRegulations")

BASE_URL = "https://mra.gov.pg"
REGULATIONS_URL = f"{BASE_URL}/investment/miningregulations/"
SAMPLE_DIR = Path(__file__).parent / "sample"
SOURCE_ID = "PG/MRA-MiningRegulations"

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

CRAWL_DELAY = 1


def _title_from_filename(pdf_url: str) -> str:
    """Derive a readable title from the PDF filename."""
    filename = unquote(pdf_url.split('/')[-1])
    # Remove .pdf extension
    name = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    # Remove leading numbers and dots (e.g., "2.MINING_ACT-1992" -> "MINING_ACT-1992")
    name = re.sub(r'^\d+\.', '', name)
    # Replace hyphens and underscores with spaces
    name = name.replace('-', ' ').replace('_', ' ')
    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


class MRAMiningRegulationsScraper(BaseScraper):
    """Scraper for PG/MRA-MiningRegulations."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

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
            resp = self.session.get(pdf_url, timeout=120)
            resp.raise_for_status()
            if len(resp.content) < 100:
                return None
            return resp.content
        except requests.RequestException as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {e}")
            return None

    def _extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF bytes using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not available")
            return None

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
                        try:
                            page.flush_cache(); page.get_textmap.cache_clear()
                        except Exception:
                            pass
                    return "\n\n".join(pages_text) if pages_text else None
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")
                return None

    def _collect_pdf_links(self, html: str) -> list:
        """Extract all PDF links from the regulations page."""
        pdf_urls = re.findall(r'href="([^"]*\.pdf[^"]*)"', html)
        seen = set()
        items = []
        for url in pdf_urls:
            url = url.strip()
            if url in seen:
                continue
            seen.add(url)
            doc_hash = hashlib.md5(url.encode()).hexdigest()[:10]
            title = _title_from_filename(url)
            items.append({
                'doc_id': doc_hash,
                'title': title,
                'pdf_url': url,
            })
        return items

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        return {
            '_id': f"PG-MRA-{raw['doc_id']}",
            '_source': SOURCE_ID,
            '_type': 'legislation',
            '_fetched_at': datetime.now(timezone.utc).isoformat(),
            'title': raw['title'],
            'text': raw['text'],
            'date': raw.get('date', ''),
            'url': raw['pdf_url'],
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Yield all documents."""
        logger.info(f"Fetching regulations page: {REGULATIONS_URL}")
        html = self._get_page(REGULATIONS_URL)
        if not html:
            logger.error("Could not fetch regulations page")
            return

        items = self._collect_pdf_links(html)
        logger.info(f"Found {len(items)} PDF documents")

        total_yielded = 0
        for item in items:
            logger.info(f"  [{total_yielded + 1}/{len(items)}] {item['title']}")
            logger.info(f"      PDF: {item['pdf_url'][:80]}")

            pdf_bytes = self._download_pdf(item['pdf_url'])
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
                SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
                sample_path = SAMPLE_DIR / f"{record['_id']}.json"
                with open(sample_path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)

            yield record
            total_yielded += 1

        logger.info(f"\nTotal documents yielded: {total_yielded}")

    def fetch_updates(self, since: str = None) -> Generator[dict, None, None]:
        """Fetch updates — re-fetch all for small static collection."""
        yield from self.fetch_all(sample=False)

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        try:
            resp = self.session.get(REGULATIONS_URL, timeout=15)
            if resp.status_code == 200 and '.pdf' in resp.text:
                logger.info("Connection test PASSED")
                return True
            logger.error(f"Connection test FAILED: status {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"Connection test FAILED: {e}")
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PG/MRA-MiningRegulations scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Only fetch sample records")
    parser.add_argument("--full", action="store_true", help="Full fetch")
    args = parser.parse_args()

    scraper = MRAMiningRegulationsScraper()

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
