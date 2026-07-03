#!/usr/bin/env python3
"""
MM/MyanmarTradePortal -- Myanmar National Trade Portal Legal Documents

Fetches trade-related laws and regulations from the Myanmar National Trade Portal.

Strategy:
  - Paginate through /en/legals?page=N to collect document IDs
  - For each document, fetch /en/legal/{id} for metadata
  - Download attached PDF and extract text via pdfplumber
  - Fall back to description text if PDF extraction fails

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # 10+ sample records
  python bootstrap.py test               # Connectivity test
"""

import sys
import json
import logging
import re
import time
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.MM.MyanmarTradePortal")

BASE_URL = "https://www.myanmartradeportal.gov.mm"
HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "text/html",
    "Accept-Language": "en",
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


class MyanmarTradePortalScraper(BaseScraper):
    """
    Scraper for MM/MyanmarTradePortal.
    Fetches trade-related laws from Myanmar National Trade Portal.
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=BASE_URL,
            headers=HEADERS,
            timeout=60,
        )

    def _list_page(self, page: int = 1) -> List[str]:
        """Fetch a listing page and extract legal document IDs."""
        self.rate_limiter.wait()
        url = f"/en/legals?page={page}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            html = resp.text
            ids = re.findall(r'en/legal/(\d+)', html)
            unique_ids = list(dict.fromkeys(ids))  # deduplicate preserving order
            logger.info(f"Page {page}: found {len(unique_ids)} documents")
            return unique_ids
        except Exception as e:
            logger.warning(f"Failed to fetch page {page}: {e}")
            return []

    def _fetch_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single legal document page and extract metadata + PDF text."""
        self.rate_limiter.wait()
        try:
            resp = self.client.get(f"/en/legal/{doc_id}")
            resp.raise_for_status()
            html = resp.text

            # Extract title
            title_match = re.search(r'<h\d[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)', html)
            if not title_match:
                title_match = re.search(r'<h\d[^>]*>([^<]{10,})</h\d>', html)
            title = title_match.group(1).strip() if title_match else f"Legal Document {doc_id}"

            # Extract date
            date_str = ""
            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', html)
            if not date_match:
                date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', html)
            if date_match:
                d = date_match.group(1)
                # Normalize date
                if len(d.split("/")[0]) <= 2 or len(d.split("-")[0]) <= 2:
                    parts = re.split(r'[-/]', d)
                    if len(parts) == 3 and len(parts[2]) == 4:
                        date_str = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                else:
                    date_str = d.replace("/", "-")

            # Extract description text from paragraphs
            desc_parts = []
            for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
                text = re.sub(r'<[^>]+>', ' ', p_match.group(1)).strip()
                text = re.sub(r'\s+', ' ', text)
                if len(text) > 30 and 'picture_as_pdf' not in text:
                    desc_parts.append(text)
            description = "\n".join(desc_parts)

            # Extract PDF URLs
            pdf_urls = list(dict.fromkeys(
                re.findall(r'href="([^"]*\.pdf)"', html)
            ))

            # Download and extract PDF text
            pdf_text = ""
            for pdf_url in pdf_urls[:2]:  # Try first 2 PDFs
                try:
                    self.rate_limiter.wait()
                    pdf_resp = self.client.get(pdf_url)
                    pdf_resp.raise_for_status()
                    extracted = extract_pdf_text(pdf_resp.content)
                    if extracted and len(extracted) > len(pdf_text):
                        pdf_text = extracted
                except Exception as e:
                    logger.warning(f"PDF download failed for {pdf_url}: {e}")

            # Combine text: prefer PDF text, fall back to description
            full_text = pdf_text if pdf_text else description

            if not full_text or len(full_text) < 50:
                logger.warning(f"Insufficient text for doc {doc_id}: {len(full_text)} chars")
                return None

            return {
                "doc_id": doc_id,
                "title": title,
                "date": date_str,
                "description": description,
                "full_text": full_text,
                "pdf_urls": pdf_urls,
                "text_source": "pdf" if pdf_text else "description",
            }

        except Exception as e:
            logger.warning(f"Failed to fetch document {doc_id}: {e}")
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legal documents from the trade portal."""
        total = 0
        page = 1
        max_pages = 35

        while page <= max_pages:
            ids = self._list_page(page)
            if not ids:
                break

            for doc_id in ids:
                doc = self._fetch_document(doc_id)
                if doc:
                    total += 1
                    yield doc

            page += 1

        logger.info(f"Fetched {total} documents total")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield recent documents (re-fetches page 1-3 for latest)."""
        for page in range(1, 4):
            ids = self._list_page(page)
            for doc_id in ids:
                doc = self._fetch_document(doc_id)
                if doc:
                    yield doc

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        doc_id = raw.get("doc_id", "")
        title = raw.get("title", "")
        full_text = raw.get("full_text", "")
        date_str = raw.get("date", "")

        return {
            "_id": f"MM-MTP-{doc_id}",
            "_source": "MM/MyanmarTradePortal",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": full_text,
            "date": date_str,
            "url": f"{BASE_URL}/en/legal/{doc_id}",
            "description": raw.get("description", ""),
            "pdf_urls": raw.get("pdf_urls", []),
            "text_source": raw.get("text_source", ""),
            "language": "en",
        }

    def test_connection(self):
        """Quick connectivity test."""
        print("Testing Myanmar Trade Portal...")
        try:
            ids = self._list_page(1)
            print(f"  Page 1: {len(ids)} documents")
            if ids:
                doc = self._fetch_document(ids[0])
                if doc:
                    print(f"  Title: {doc['title'][:60]}")
                    print(f"  Text source: {doc['text_source']}")
                    print(f"  Text length: {len(doc['full_text'])} chars")
                    print(f"  PDFs: {len(doc['pdf_urls'])}")
        except Exception as e:
            print(f"  ERROR: {e}")
        print("\nTest complete!")


def main():
    scraper = MyanmarTradePortalScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update|test] [--sample] [--sample-size N]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 12
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command == "test":
        scraper.test_connection()
    elif command in ("bootstrap", "bootstrap-fast"):
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
            print(f"\nSample complete: {stats.get('sample_records_saved', 0)} records saved")
        else:
            stats = scraper.bootstrap()
            print(f"\nBootstrap complete: {stats['records_new']} new")
        print(json.dumps(stats, indent=2))
    elif command == "update":
        stats = scraper.update()
        print(json.dumps(stats, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
