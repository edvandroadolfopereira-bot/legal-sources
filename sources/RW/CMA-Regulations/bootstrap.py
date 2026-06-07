#!/usr/bin/env python3
"""
RW/CMA-Regulations -- Rwanda Capital Market Authority regulatory framework

Fetches the Rwanda Capital Market Authority (CMA) legal framework published at
cma.rw. The site runs TYPO3; the "Regulatory Framework" section lists each
instrument in a `docs-item` card (title + date + direct PDF download under
/fileadmin/user_upload/). We parse those cards, download each PDF, and extract
full text with pdfplumber. Rwandan instruments are published trilingually
(Kinyarwanda / English / French) in Official Gazette format.

Covered categories:
  - laws            (e.g. Law establishing the CMA, Law on Collective Investment
                     Schemes, Law regulating Virtual Asset Business)
  - regulations     (e.g. Corporate Governance Code, CSD operations, REITs,
                     leveraged FX trading, AML sanctions)
  - guidelines      (e.g. GSS+ bonds issuance, Fintech sandbox, ML/FT prevention)
  - orders          (ministerial orders)
  - directives      (CMA directives)
  - eac-directives  (East African Community directives, where present)

~30 instruments, all born-digital PDFs with extractable text.

Strategy:
  1. Fetch each regulatory-framework category page
  2. Parse the docs-item cards (title, date, PDF URL)
  3. Download each PDF, extract text with pdfplumber
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
import html
import hashlib
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Dict
from urllib.parse import urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.RW.CMA-Regulations")

BASE_URL = "https://www.cma.rw"
SAMPLE_DIR = Path(__file__).parent / "sample"
SOURCE_ID = "RW/CMA-Regulations"

CATEGORIES = [
    "laws",
    "orders",
    "regulations",
    "guidelines",
    "directives",
    "eac-directives",
]

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

CRAWL_DELAY = 1
MIN_TEXT_CHARS = 400


def _parse_date(raw: str) -> str:
    """Convert a MM/DD/YYYY card date to ISO 8601 (YYYY-MM-DD)."""
    raw = (raw or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if not m:
        return ""
    mm, dd, yyyy = m.groups()
    try:
        return datetime(int(yyyy), int(mm), int(dd)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


class CMARegulationsScraper(BaseScraper):
    """Scraper for RW/CMA-Regulations."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_page(self, url: str) -> Optional[str]:
        time.sleep(CRAWL_DELAY)
        try:
            resp = self.session.get(url, timeout=45)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    @staticmethod
    def _parse_items(page_html: str, category: str) -> List[Dict]:
        """Parse docs-item cards (title, date, PDF URL) from a category page."""
        items = []
        # Each card opens with the title h3; everything up to the next title
        # belongs to that card.
        parts = re.split(r'<h3 class="docs-item-title">', page_html)
        for part in parts[1:]:
            title = re.sub(r"<[^>]+>", "", part.split("</h3>")[0])
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()

            dm = re.search(r'docs-item-date">\s*([\d/]{8,10})', part)
            date = _parse_date(dm.group(1)) if dm else ""

            um = re.search(
                r'href=["\']([^"\']*fileadmin/user_upload/[^"\']+\.pdf[^"\']*)["\']',
                part,
                re.I,
            )
            if not um or not title:
                continue
            pdf_url = urljoin(BASE_URL, html.unescape(um.group(1).strip()))
            items.append(
                {"title": title, "date": date, "pdf_url": pdf_url, "category": category}
            )
        return items

    def _download_pdf(self, pdf_url: str) -> Optional[bytes]:
        time.sleep(CRAWL_DELAY)
        try:
            resp = self.session.get(pdf_url, timeout=180)
            resp.raise_for_status()
            if len(resp.content) < 100:
                return None
            return resp.content
        except requests.RequestException as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {e}")
            return None

    def _extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> Optional[str]:
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
                    return "\n\n".join(pages_text) if pages_text else None
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")
                return None

    def normalize(self, raw: dict) -> dict:
        return {
            "_id": f"RW-CMA-{raw['doc_id']}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date", ""),
            "url": raw["pdf_url"],
            "category": raw.get("category", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        # Collect items across all categories first.
        all_items: List[Dict] = []
        for cat in CATEGORIES:
            url = f"{BASE_URL}/regulatory-framework/{cat}"
            page = self._get_page(url)
            if not page:
                continue
            items = self._parse_items(page, cat)
            logger.info(f"  {cat}: {len(items)} items")
            all_items.extend(items)

        # Deduplicate by PDF URL (an instrument can appear in two categories).
        seen = set()
        unique = []
        for it in all_items:
            if it["pdf_url"] in seen:
                continue
            seen.add(it["pdf_url"])
            unique.append(it)
        logger.info(f"Total unique documents: {len(unique)}")

        total_yielded = 0
        skipped = 0
        for it in unique:
            logger.info(f"  [{total_yielded + 1}] {it['title'][:60]}")
            logger.info(f"      PDF: {it['pdf_url'][:90]}")

            pdf_bytes = self._download_pdf(it["pdf_url"])
            if not pdf_bytes:
                logger.warning("      Skipping — could not download PDF")
                continue

            text = self._extract_text_from_pdf_bytes(pdf_bytes)
            if not text or len(text) < MIN_TEXT_CHARS:
                logger.warning(
                    f"      Skipping — insufficient text "
                    f"({len(text) if text else 0} chars)"
                )
                skipped += 1
                continue

            logger.info(f"      Extracted {len(text)} chars")

            it["doc_id"] = hashlib.md5(it["pdf_url"].encode()).hexdigest()[:10]
            it["text"] = text
            record = self.normalize(it)

            if sample:
                SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
                sample_path = SAMPLE_DIR / f"{record['_id']}.json"
                with open(sample_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)

            yield record
            total_yielded += 1

        logger.info(
            f"\nTotal documents yielded: {total_yielded} ({skipped} skipped)"
        )

    def fetch_updates(self, since: str = None) -> Generator[dict, None, None]:
        yield from self.fetch_all(sample=False)

    def test_connection(self) -> bool:
        try:
            resp = self.session.get(
                f"{BASE_URL}/regulatory-framework/laws", timeout=30
            )
            if resp.status_code == 200 and "docs-item" in resp.text:
                logger.info("Connection test PASSED")
                return True
            logger.error(f"Connection test FAILED: status {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"Connection test FAILED: {e}")
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RW/CMA-Regulations scraper")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Only fetch sample records")
    parser.add_argument("--full", action="store_true", help="Full fetch")
    args = parser.parse_args()

    scraper = CMARegulationsScraper()

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
