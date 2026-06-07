#!/usr/bin/env python3
"""
GE/NBG-LegalActs -- Georgia National Bank Legal Acts & Regulations

Fetches legal acts (decrees, orders, regulations) from the National Bank
of Georgia's internal API, then downloads attached PDF documents and
extracts full text via pdfplumber.

Strategy:
  - Discovery: Paginated JSON API at /gw/api/pg/pages/static/legalacts
  - Full text: PDF attachments at /fm/{path} — extracted with pdfplumber
  - Languages: Georgian (319 docs) and English (84 docs); we fetch both,
    preferring English where available and falling back to Georgian.

Endpoints:
  - List:    GET /gw/api/pg/pages/static/legalacts?take=50&skip=N
             Header Accept-Language: en | ka
  - Detail:  GET /gw/api/pg/pages/static/legalacts/{id}/details
  - PDF:     GET /fm/{file_path}

Data:
  - ~319 regulatory documents (orders, decrees, regulations)
  - Categories: Banking Supervision, Payment Systems, Securities,
    Monetary Policy, Consumer Protection, Sustainable Finance, etc.
  - No authentication required

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 12+ sample records
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import io
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any
from urllib.parse import quote

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GE.NBG-LegalActs")

# API and file base URLs
API_BASE = "https://nbg.gov.ge/gw/api/pg/pages/static/legalacts"
FILE_BASE = "https://nbg.gov.ge/fm/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed — cannot extract PDF text")
        return ""
    try:
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(text)
        full_text = "\n\n".join(pages_text)
        # Normalize whitespace
        full_text = re.sub(r"\r\n", "\n", full_text)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        return full_text.strip()
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


class NBGLegalActsScraper(BaseScraper):
    """
    Scraper for GE/NBG-LegalActs -- Georgia National Bank Legal Acts.
    Country: GE
    URL: https://nbg.gov.ge/en/legal-acts/acts

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str, params: Optional[Dict] = None,
             headers: Optional[Dict] = None, timeout: int = 60) -> requests.Response:
        """Make HTTP GET request with rate limiting."""
        self.rate_limiter.wait()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed for {url}: {e}")
            raise

    def _fetch_page(self, lang: str, skip: int = 0, take: int = 50) -> Dict[str, Any]:
        """Fetch a page of legal acts from the API."""
        params = {"take": take, "skip": skip}
        lang_headers = {"Accept-Language": lang}
        resp = self._get(API_BASE, params=params, headers=lang_headers)
        return resp.json()

    def _download_pdf(self, file_path: str) -> bytes:
        """Download a PDF file from the NBG file server."""
        url = FILE_BASE + quote(file_path, safe="/")
        resp = self._get(url, timeout=90)
        return resp.content

    def _extract_text_from_files(self, files: list) -> str:
        """Download and extract text from all PDF files attached to a legal act."""
        texts = []
        for f in files:
            file_path = f.get("file", "")
            if not file_path:
                continue
            if not file_path.lower().endswith(".pdf"):
                continue
            try:
                pdf_bytes = self._download_pdf(file_path)
                text = _extract_pdf_text(pdf_bytes)
                if text:
                    texts.append(text)
            except Exception as e:
                logger.warning(f"Failed to download/extract PDF {file_path}: {e}")
        return "\n\n---\n\n".join(texts)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw API response into standard schema."""
        act_id = raw.get("id", "")
        title = raw.get("title", "")
        date_str = raw.get("date", "")
        doc_number = raw.get("documentNumber", "")
        status = raw.get("status", "")
        lang = raw.get("_lang", "ka")
        text = raw.get("_extracted_text", "")

        # Category
        category = ""
        cat_obj = raw.get("category")
        if isinstance(cat_obj, dict):
            category = cat_obj.get("title", "")

        # Sub-category
        sub_category = ""
        sub_obj = raw.get("subCategory")
        if isinstance(sub_obj, dict):
            sub_category = sub_obj.get("title", "")

        # Document type
        doc_type = ""
        dtype_obj = raw.get("documentType")
        if isinstance(dtype_obj, dict):
            doc_type = dtype_obj.get("title", "")

        # Recipient
        recipient = ""
        recip_obj = raw.get("recipient")
        if isinstance(recip_obj, dict):
            recipient = recip_obj.get("title", "")

        # Parse date
        parsed_date = ""
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                parsed_date = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                parsed_date = date_str[:10] if len(date_str) >= 10 else date_str

        return {
            "_id": f"nbg-act-{act_id}",
            "_source": "GE/NBG-LegalActs",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": parsed_date,
            "url": "https://nbg.gov.ge/en/legal-acts/acts",
            "document_number": doc_number,
            "status": status,
            "category": category,
            "sub_category": sub_category,
            "document_type": doc_type,
            "recipient": recipient,
            "language": lang,
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all legal acts with full text from PDFs.

        Yields raw records with _extracted_text and _lang fields populated.
        The base class calls normalize() on each yielded record.
        """
        total_fetched = 0
        seen_ids = set()

        # Fetch English first, then Georgian for remaining
        for lang, lang_label in [("en", "English"), ("ka", "Georgian")]:
            logger.info(f"Fetching {lang_label} legal acts...")
            skip = 0
            take = 50

            # Get total count first
            try:
                first_page = self._fetch_page(lang, skip=0, take=1)
                total = first_page.get("meta", {}).get("total", 0)
                logger.info(f"  {lang_label}: {total} total acts")
            except Exception as e:
                logger.error(f"Failed to fetch {lang_label} acts: {e}")
                continue

            while True:
                try:
                    result = self._fetch_page(lang, skip=skip, take=take)
                except Exception as e:
                    logger.error(f"Failed to fetch page skip={skip}: {e}")
                    break

                items = result.get("data", [])
                if not items:
                    break

                for item in items:
                    act_id = item.get("id")
                    if act_id in seen_ids:
                        continue
                    seen_ids.add(act_id)

                    files = item.get("files", [])
                    if not files:
                        logger.warning(f"Act {act_id} has no files, skipping")
                        continue

                    # Extract full text from PDFs
                    text = self._extract_text_from_files(files)
                    if not text:
                        logger.warning(f"No text extracted for act {act_id}: {item.get('title','')[:60]}")
                        continue

                    item["_extracted_text"] = text
                    item["_lang"] = lang

                    yield item
                    total_fetched += 1

                    if total_fetched % 20 == 0:
                        logger.info(f"  Fetched {total_fetched} records so far...")

                skip += take
                meta_total = result.get("meta", {}).get("total", 0)
                if meta_total and skip >= meta_total:
                    break

        logger.info(f"Total fetched: {total_fetched}")

    def fetch_updates(self, since) -> Generator[Dict[str, Any], None, None]:
        """Fetch documents updated since a given date.

        The API does not support date filtering, so we do a full fetch
        and filter by date client-side.
        """
        if isinstance(since, datetime):
            since_str = since.strftime("%Y-%m-%d")
        else:
            since_str = str(since)[:10]
        logger.info(f"Fetching updates since {since_str} (full scan, client-side filter)")
        for raw in self.fetch_all():
            date_str = raw.get("date", "")
            if date_str and date_str[:10] >= since_str:
                yield raw


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GE/NBG-LegalActs bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Only fetch sample records (for validation)")
    parser.add_argument("--since", type=str, default=None,
                        help="Date for incremental update (YYYY-MM-DD)")
    args = parser.parse_args()

    scraper = NBGLegalActsScraper()

    if args.command == "test":
        try:
            result = scraper._fetch_page("en", skip=0, take=1)
            total = result.get("meta", {}).get("total", 0)
            logger.info(f"API connectivity OK. {total} English legal acts available.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"API test failed: {e}")
            sys.exit(1)

    elif args.command == "bootstrap":
        stats = scraper.bootstrap(sample_mode=args.sample, sample_size=15)
        logger.info(f"Bootstrap complete: {stats}")

    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap_fast()
        logger.info(f"Bootstrap-fast complete: {stats}")

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {stats}")


if __name__ == "__main__":
    main()
