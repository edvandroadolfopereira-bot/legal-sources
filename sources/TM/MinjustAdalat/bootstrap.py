#!/usr/bin/env python3
"""
TM/MinjustAdalat -- Turkmenistan Ministry of Justice Legal Information Center

Fetches state-registered normative legal acts from the Legal Information Center
(Hukuk Maglumatlar Merkezi) at minjust.gov.tm.

Strategy:
  1. POST /api/front/laws/search to get all document records (356 total)
  2. Download PDFs for each document (Turkmen preferred, Russian fallback)
  3. Extract full text from PDFs using pdfplumber
  4. Normalize into standard schema

Usage:
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap --full     # Full bootstrap
  python bootstrap.py bootstrap-fast       # Alias for --full
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
import io
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from html import unescape

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.TM.MinjustAdalat")

API_BASE = "https://minjust.gov.tm/api"
SITE_BASE = "https://minjust.gov.tm"
USER_AGENT = "LegalDataHunter/1.0 (legal research; open data collection)"


def _clean_text(text: str) -> str:
    """Clean extracted text: strip HTML, decode entities, normalize whitespace."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\ufeff", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}, trying PyPDF2")
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(pages_text)
        except Exception as e2:
            logger.error(f"PyPDF2 also failed: {e2}")
            return ""


class MinjustAdalatScraper(BaseScraper):
    """Scraper for Turkmenistan MoJ Legal Information Center."""

    def __init__(self, source_dir: str = None):
        if source_dir is None:
            source_dir = str(Path(__file__).parent)
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en",
        })

    def _search_all(self) -> List[Dict[str, Any]]:
        """Fetch all documents via the search API."""
        url = f"{API_BASE}/front/laws/search"
        payload = {
            "search": "",
            "years": [],
            "laws": [],
            "lawConfirmDepartments": [],
        }
        for attempt in range(3):
            try:
                resp = self.session.post(url, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                total = data.get("resultsCount", len(results))
                logger.info(f"Search returned {len(results)}/{total} documents")
                return results
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Search attempt {attempt+1} failed: {e}")
                    time.sleep(3 * (attempt + 1))
                else:
                    raise

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download a PDF file."""
        if not url or not url.startswith("http"):
            return None
        for attempt in range(3):
            try:
                resp = self.session.get(
                    url,
                    timeout=60,
                    headers={"Accept": "application/pdf"},
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                if len(resp.content) < 100:
                    return None
                return resp.content
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"PDF download attempt {attempt+1} failed for {url}: {e}")
                    time.sleep(2 * (attempt + 1))
                else:
                    logger.error(f"PDF download failed after 3 attempts: {url}")
                    return None

    def _get_best_text(self, record: Dict[str, Any]) -> str:
        """Get full text: download PDF and extract text."""
        files = record.get("files", {})
        # Try Turkmen first, then Russian
        for lang in ["tm", "ru", "en"]:
            pdf_url = files.get(lang, "")
            if not pdf_url:
                continue
            logger.info(f"  Downloading PDF ({lang}): {pdf_url}")
            pdf_bytes = self._download_pdf(pdf_url)
            if pdf_bytes:
                text = _extract_pdf_text(pdf_bytes)
                if text and len(text) > 100:
                    logger.info(f"  Extracted {len(text)} chars from {lang} PDF")
                    return text
                else:
                    logger.warning(f"  PDF text too short ({len(text)} chars) from {lang}")
        # Fallback to API text snippet
        api_text = record.get("text", {})
        for lang in ["tm", "ru", "en"]:
            t = api_text.get(lang, "")
            if t and len(t) > 50:
                return _clean_text(t)
        return ""

    def _get_title(self, record: Dict[str, Any]) -> str:
        """Get best title: prefer English, then Turkmen, then Russian."""
        titles = record.get("title", {})
        for lang in ["en", "tm", "ru"]:
            t = titles.get(lang, "")
            if t:
                return t
        return f"Document {record.get('id', 'unknown')}"

    def _get_category(self, record: Dict[str, Any]) -> str:
        """Get law category from the laws field."""
        laws = record.get("laws", [])
        if laws and laws[0].get("title"):
            titles = laws[0]["title"]
            return titles.get("en") or titles.get("tm") or titles.get("ru") or ""
        return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw record into the standard schema."""
        doc_id = raw.get("id", "")
        title = self._get_title(raw)
        text = raw.get("_extracted_text", "")
        category = self._get_category(raw)

        files = raw.get("files", {})
        pdf_url = files.get("tm") or files.get("ru") or files.get("en") or ""

        return {
            "_id": f"TM-minjust-adalat-{doc_id}",
            "_source": "TM/MinjustAdalat",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "title_tm": raw.get("title", {}).get("tm", ""),
            "title_ru": raw.get("title", {}).get("ru", ""),
            "title_en": raw.get("title", {}).get("en", ""),
            "text": text,
            "category": category,
            "url": pdf_url if pdf_url else f"{SITE_BASE}/hukuk/merkezi",
            "date": None,
            "source_id": str(doc_id),
            "pdf_url_tm": files.get("tm", ""),
            "pdf_url_ru": files.get("ru", ""),
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all documents with full text."""
        records = self._search_all()
        for i, record in enumerate(records):
            logger.info(f"Processing {i+1}/{len(records)}: {self._get_title(record)}")
            text = self._get_best_text(record)
            record["_extracted_text"] = text
            yield record
            time.sleep(1.5)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch updates since a date. Not supported — yields all."""
        yield from self.fetch_all()

    def fetch_sample(self, count: int = 15) -> Generator[Dict[str, Any], None, None]:
        """Fetch a sample of documents."""
        records = self._search_all()
        # Pick first `count` records that have PDF files
        selected = []
        for r in records:
            files = r.get("files", {})
            if files.get("tm") or files.get("ru"):
                selected.append(r)
            if len(selected) >= count:
                break
        logger.info(f"Selected {len(selected)} sample records")
        for i, record in enumerate(selected):
            logger.info(f"Processing sample {i+1}/{len(selected)}: {self._get_title(record)}")
            text = self._get_best_text(record)
            record["_extracted_text"] = text
            yield record
            time.sleep(1.5)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TM/MinjustAdalat bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Full bootstrap")
    args = parser.parse_args()

    scraper = MinjustAdalatScraper()
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command == "test":
        logger.info("Testing connectivity...")
        try:
            records = scraper._search_all()
            logger.info(f"API accessible: {len(records)} documents found")
            if records:
                r = records[0]
                logger.info(f"First record: {scraper._get_title(r)}")
                files = r.get("files", {})
                for lang in ["tm", "ru"]:
                    if files.get(lang):
                        logger.info(f"  PDF ({lang}): {files[lang]}")
            print("OK")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            print("FAIL")
            sys.exit(1)
        return

    is_sample = args.sample or (args.command == "bootstrap" and not args.full)
    is_fast = args.command == "bootstrap-fast"

    if is_sample and not is_fast:
        gen = scraper.fetch_sample(15)
    else:
        gen = scraper.fetch_all()

    count = 0
    text_count = 0
    for raw in gen:
        normalized = scraper.normalize(raw)
        if normalized.get("text") and len(normalized["text"]) > 100:
            text_count += 1

        if is_sample or count < 20:
            fname = sample_dir / f"{normalized['_id']}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)

        count += 1
        if is_sample and count >= 15:
            break

    logger.info(f"Done: {count} records, {text_count} with full text")
    if count == 0:
        logger.error("No records fetched!")
        sys.exit(1)
    if text_count < min(count, 5):
        logger.warning(f"Low text extraction rate: {text_count}/{count}")


if __name__ == "__main__":
    main()
