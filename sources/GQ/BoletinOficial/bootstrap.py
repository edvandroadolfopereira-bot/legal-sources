#!/usr/bin/env python3
"""
GQ/BoletinOficial -- Equatorial Guinea Official State Gazette

Fetches laws, decrees, and regulations from boe.gob.gq.

Strategy:
  - POST to /resultados with empty search to get all documents + session cookie
  - Parse initial HTML results (10 per page)
  - Paginate via GET /masresultados?offset=N with session cookies
  - Download each PDF and extract full text with pdfplumber
  - ~146 documents total

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py update             # Incremental update
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
"""

import sys
import json
import logging
import re
import io
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GQ.BoletinOficial")

BASE_URL = "https://boe.gob.gq"
SEARCH_URL = f"{BASE_URL}/resultados"
PAGINATION_URL = f"{BASE_URL}/masresultados"
SOURCE_ID = "GQ/BoletinOficial"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (research; +https://legaldatahunter.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
}

SAMPLE_LIMIT = 15
PAGE_SIZE = 10

# Spanish month names for date parsing
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_html(s: str) -> str:
    import html as html_mod
    s = re.sub(r"<[^>]+>", "", s).strip()
    return html_mod.unescape(s)


def _parse_spanish_date(date_str: str) -> str:
    """Parse dates like 'viernes, 23 de abril de 2021' or 'Wednesday, 21 de April de 2021'."""
    if not date_str:
        return ""
    date_str = date_str.strip().lower()
    # Try dd/mm/yyyy
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    # Try "day, DD de month de YYYY"
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", date_str)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = SPANISH_MONTHS.get(month_name, 0)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    # Try dd-mm-yyyy
    m = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", date_str)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return _clean_text("\n\n".join(pages_text))
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return ""


def _parse_documents_from_html(html: str) -> list:
    """Parse document entries from HTML containing contenedorDoc divs."""
    docs = []
    # Split on contenedorDoc divs
    parts = re.split(r'<div class="contenedorDoc">', html)
    for part in parts[1:]:  # skip first (before first doc)
        doc = {}
        # Title
        m = re.search(r'<h4>(.*?)</h4>', part, re.DOTALL)
        doc["title"] = _strip_html(m.group(1)).strip() if m else ""
        # Date
        m = re.search(r'class="fechaDoc[^"]*"[^>]*>.*?</i>\s*(.*?)</span>', part, re.DOTALL)
        doc["date_raw"] = _strip_html(m.group(1)).strip() if m else ""
        # Class (subject area)
        m = re.search(r'class="claseDoc[^"]*"[^>]*>.*?</i>\s*(.*?)</span>', part, re.DOTALL)
        doc["subject_class"] = _strip_html(m.group(1)).strip() if m else ""
        # Category
        m = re.search(r'class="categoriaDoc[^"]*"[^>]*>.*?</i>\s*(.*?)</span>', part, re.DOTALL)
        doc["category"] = _strip_html(m.group(1)).strip() if m else ""
        # PDF URL
        m = re.search(r'href="(https://boe\.gob\.gq/files/[^"]+\.pdf)"', part)
        doc["pdf_url"] = m.group(1) if m else ""
        # Summary
        m = re.search(r'class="resumenDoc"[^>]*>(.*?)</div>', part, re.DOTALL)
        if m:
            summary_html = m.group(1)
            # Get text before "..." and after
            summary = _strip_html(re.sub(r'<button[^>]*>.*?</button>', '', summary_html))
            summary = re.sub(r'Ver resumen completo', '', summary).strip()
            summary = re.sub(r'\.\.\.', '', summary).strip()
            doc["summary"] = summary
        else:
            doc["summary"] = ""

        if doc["pdf_url"]:
            docs.append(doc)

    return docs


class SourceScraper(BaseScraper):
    """
    Scraper for: Boletín Oficial del Estado de Guinea Ecuatorial
    Country: GQ
    URL: https://boe.gob.gq/

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url="",
            headers=HEADERS,
        )
        # Disable SSL verification for this source (known cert issue)
        self.client.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _fetch_all_document_metadata(self) -> list:
        """Fetch all document metadata via search + pagination."""
        all_docs = []

        # Initial search POST
        logger.info("POSTing search to get all documents...")
        resp = self.client.session.post(
            SEARCH_URL,
            data={
                "titulo": "",
                "categoria": "",
                "texto": "",
                "operadortexto": "AND",
                "clase": "",
                "numero": "",
                "fechadesde": "",
                "fechahasta": "",
                "orden": "D",
                "csv": "",
            },
            headers=HEADERS,
            verify=False,
        )
        resp.raise_for_status()

        # Parse total count
        m = re.search(r'Se han encontrado <strong>(\d+)</strong>', resp.text)
        total = int(m.group(1)) if m else 0
        logger.info(f"Total documents found: {total}")

        # Parse initial page
        docs = _parse_documents_from_html(resp.text)
        all_docs.extend(docs)
        logger.info(f"Parsed {len(docs)} documents from initial page")

        # Paginate
        offset = PAGE_SIZE + 1  # Server uses 1-based offset
        while len(all_docs) < total:
            time.sleep(1)
            logger.info(f"Fetching offset={offset} ({len(all_docs)}/{total})...")
            resp = self.client.session.get(
                f"{PAGINATION_URL}?offset={offset}",
                headers=HEADERS,
                verify=False,
            )
            if resp.status_code != 200 or len(resp.text.strip()) < 10:
                logger.info("No more results from pagination")
                break
            docs = _parse_documents_from_html(resp.text)
            if not docs:
                break
            all_docs.extend(docs)
            offset += PAGE_SIZE

        logger.info(f"Total metadata entries collected: {len(all_docs)}")
        return all_docs

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all documents with full text from PDF."""
        all_docs = self._fetch_all_document_metadata()

        seen_urls = set()
        for i, doc in enumerate(all_docs):
            pdf_url = doc.get("pdf_url", "")
            if not pdf_url or pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)

            logger.info(f"[{i+1}/{len(all_docs)}] Downloading: {doc['title'][:60]}...")
            time.sleep(1)

            try:
                resp = self.client.session.get(pdf_url, headers=HEADERS, verify=False, timeout=60)
                if resp.status_code != 200:
                    logger.warning(f"HTTP {resp.status_code} for {pdf_url}")
                    continue
                pdf_bytes = resp.content
                if len(pdf_bytes) < 500:
                    logger.warning(f"PDF too small ({len(pdf_bytes)} bytes): {pdf_url}")
                    continue
            except Exception as e:
                logger.warning(f"Download failed for {pdf_url}: {e}")
                continue

            text = _extract_pdf_text(pdf_bytes)
            if not text:
                logger.warning(f"No text extracted from {pdf_url}")
                continue

            doc["text"] = text
            doc["pdf_size"] = len(pdf_bytes)
            yield doc

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """No date-based filtering available; fall back to full fetch."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title", "").strip()
        pdf_url = raw.get("pdf_url", "")
        doc_id = hashlib.sha256(pdf_url.encode()).hexdigest()[:16]
        date = _parse_spanish_date(raw.get("date_raw", ""))

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": date or None,
            "date_raw": raw.get("date_raw", ""),
            "category": raw.get("category", ""),
            "subject_class": raw.get("subject_class", ""),
            "summary": raw.get("summary", ""),
            "url": pdf_url,
            "pdf_url": pdf_url,
            "pdf_size": raw.get("pdf_size", 0),
            "language": "es",
        }


# ── CLI Entry Point ───────────────────────────────────────────────

def main():
    scraper = SourceScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update] [--sample] [--sample-size N]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 10
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command in ("bootstrap", "bootstrap-fast"):
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
            print(f"\nSample complete: {stats.get('sample_records_saved', 0)} records saved to sample/")
        else:
            stats = scraper.bootstrap()
            print(f"\nBootstrap complete: {stats['records_new']} new, {stats['records_updated']} updated, {stats['records_skipped']} skipped")
    elif command == "update":
        stats = scraper.update()
        print(f"\nUpdate complete: {stats['records_new']} new, {stats['records_updated']} updated")
    elif command == "test":
        print("Testing connectivity...")
        import requests
        resp = requests.get(BASE_URL, headers=HEADERS, verify=False, timeout=15)
        print(f"Status: {resp.status_code}, Length: {len(resp.text)}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    if command != "test":
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
