#!/usr/bin/env python3
"""
DO/ConsultoriaJuridica -- Consultoría Jurídica del Poder Ejecutivo
(Dominican Republic)

Fetches the full text of Dominican legislation from the Executive Branch's
Legal Advisory Office database: laws, decrees, regulations, resolutions,
and Official Gazette entries dating back to 1926.

Strategy:
  The site at consultoria.gov.do/consulta/ uses an ASP.NET MVC AJAX form.
  1. GET the main page to obtain a CSRF anti-forgery token + session cookies.
  2. POST to /Consulta/Home/Search with DocumentTypeCode=0 (all) and year
     filter to enumerate documents. Returns an HTML table with document IDs.
  3. GET /consulta/Home/DocumentInfo?documentId=X for JSON metadata (title,
     number, gazette, dates, president, consultor).
  4. GET /Consulta/Home/FileManagement?documentId=X&managementType=1 to
     download the PDF.
  5. Extract full text from the PDF using pdfminer.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import re
import io
import time
import logging
import html as html_module
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.DO.ConsultoriaJuridica")

BASE_URL = "https://www.consultoria.gov.do"
SEARCH_URL = f"{BASE_URL}/Consulta/Home/Search?Length=7"
INFO_URL = f"{BASE_URL}/consulta/Home/DocumentInfo"
FILE_URL = f"{BASE_URL}/Consulta/Home/FileManagement"

MIN_TEXT_CHARS = 200
START_YEAR = 1926
END_YEAR = datetime.now().year

# Regex to extract document rows from the HTML table
SHOW_INFO_RE = re.compile(r'showInfo\((\d+)\)')
TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]+value="([^"]+)"')

# Parse table rows — each <tr> has: type, number, title, gazette, date, actions
ROW_RE = re.compile(
    r'<tr>\s*'
    r'<td[^>]*>\s*(.*?)\s*</td>\s*'      # doc type
    r'<td[^>]*>\s*(.*?)\s*</td>\s*'      # number
    r'<td\s+title="([^"]*)"[^>]*>\s*'    # title (in title attr)
    r'.*?</td>\s*'
    r'<td[^>]*>\s*(.*?)\s*</td>\s*'      # gazette
    r'<td[^>]*>\s*(.*?)\s*</td>\s*'      # date
    r'<td[^>]*>\s*.*?showInfo\((\d+)\)', # document ID
    re.S
)

MONTHS_ES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer."""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(io.BytesIO(pdf_bytes))
        return text.strip() if text else ""
    except ImportError:
        logger.warning("pdfminer not available, trying pdfplumber")
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages).strip()
        except ImportError:
            logger.error("No PDF library available (need pdfminer or pdfplumber)")
            return ""


def _parse_date_dd_mm_yyyy(date_str: str) -> Optional[str]:
    """Parse DD/MM/YYYY into ISO 8601."""
    date_str = date_str.strip()
    if not date_str:
        return None
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    return None


def _parse_info_date(date_str: str) -> Optional[str]:
    """Parse '28 de January de 2020' style date from DocumentInfo."""
    if not date_str or date_str == "N/A":
        return None
    m = re.match(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', date_str, re.I)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = MONTHS_ES.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


class ConsultoriaJuridicaScraper(BaseScraper):
    """Scraper for Dominican Republic Consultoría Jurídica."""

    def __init__(self, source_dir: str):
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0)",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._token = None
        self._token_time = 0

    def _get_token(self) -> str:
        """Fetch a fresh CSRF token from the main page."""
        now = time.time()
        if self._token and (now - self._token_time) < 600:
            return self._token

        resp = self.session.get(f"{BASE_URL}/consulta/", timeout=30)
        resp.raise_for_status()
        m = TOKEN_RE.search(resp.text)
        if not m:
            raise RuntimeError("Could not find anti-forgery token on page")
        self._token = m.group(1)
        self._token_time = now
        return self._token

    def _search_year(self, year: int) -> list:
        """Search all documents for a given year. Returns list of parsed rows."""
        token = self._get_token()
        data = {
            "__RequestVerificationToken": token,
            "DocumentTypeCode": "0",
            "DocumentNumber": "",
            "DocumentTitle": "",
            "GacetaOficial": "",
            "PublicationYearOperator": "1",
            "PublicationYear": str(year),
            "PublicationYearEnd": "",
        }
        resp = self.session.post(SEARCH_URL, data=data, timeout=60)
        resp.raise_for_status()

        results = []
        for m in ROW_RE.finditer(resp.text):
            doc_type = m.group(1).strip()
            doc_number = m.group(2).strip()
            title = html_module.unescape(m.group(3).strip())
            gazette = m.group(4).strip()
            date_str = m.group(5).strip()
            doc_id = m.group(6)

            results.append({
                "document_id": doc_id,
                "document_type": doc_type,
                "document_number": doc_number,
                "title": title,
                "gazette_number": gazette,
                "date_raw": date_str,
            })

        return results

    def _get_doc_info(self, doc_id: str) -> Optional[Dict]:
        """Fetch JSON metadata for a document."""
        try:
            resp = self.session.get(
                f"{INFO_URL}?documentId={doc_id}",
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.json().get("info", {})
        except Exception as e:
            logger.debug(f"DocumentInfo failed for {doc_id}: {e}")
        return None

    def _download_pdf(self, doc_id: str) -> Optional[bytes]:
        """Download PDF for a document."""
        try:
            resp = self.session.get(
                f"{FILE_URL}?documentId={doc_id}&managementType=1",
                timeout=60,
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/pdf"):
                return resp.content
        except Exception as e:
            logger.debug(f"PDF download failed for {doc_id}: {e}")
        return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all documents by iterating over years."""
        for year in range(END_YEAR, START_YEAR - 1, -1):
            logger.info(f"Searching year {year}...")
            try:
                rows = self._search_year(year)
            except Exception as e:
                logger.error(f"Search failed for year {year}: {e}")
                time.sleep(2)
                continue

            logger.info(f"Year {year}: {len(rows)} documents found")

            for row in rows:
                doc_id = row["document_id"]

                # Fetch metadata
                time.sleep(0.5)
                info = self._get_doc_info(doc_id)

                # Download and extract PDF text
                time.sleep(0.5)
                pdf_bytes = self._download_pdf(doc_id)
                if pdf_bytes:
                    text = _extract_text_from_pdf(pdf_bytes)
                else:
                    text = ""

                row["info"] = info
                row["text"] = text
                row["year"] = year
                yield row

            time.sleep(1)

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Fetch documents from the current year (incremental)."""
        current_year = datetime.now().year
        rows = self._search_year(current_year)
        for row in rows:
            doc_id = row["document_id"]
            time.sleep(0.5)
            info = self._get_doc_info(doc_id)
            time.sleep(0.5)
            pdf_bytes = self._download_pdf(doc_id)
            text = _extract_text_from_pdf(pdf_bytes) if pdf_bytes else ""
            row["info"] = info
            row["text"] = text
            row["year"] = current_year
            yield row

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw document into standard schema."""
        text = raw.get("text", "")
        if len(text) < MIN_TEXT_CHARS:
            logger.debug(f"Insufficient text ({len(text)} chars) for doc {raw.get('document_id')}")
            return None

        doc_id = raw["document_id"]
        info = raw.get("info") or {}

        # Parse date — prefer info API date, fall back to search table date
        date = None
        if info.get("FechaPromulgacion"):
            date = _parse_info_date(info["FechaPromulgacion"])
        if not date and info.get("FechaPublicacion"):
            date = _parse_info_date(info["FechaPublicacion"])
        if not date:
            date = _parse_date_dd_mm_yyyy(raw.get("date_raw", ""))

        title = info.get("Titulo") or raw.get("title") or ""
        title = html_module.unescape(title).strip()

        return {
            "_id": f"DO-CJ-{doc_id}",
            "_source": "DO/ConsultoriaJuridica",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "document_id": doc_id,
            "document_number": info.get("Numero") or raw.get("document_number", ""),
            "document_type": raw.get("document_type", ""),
            "title": title,
            "text": text,
            "date": date,
            "gazette_number": info.get("Gaceta") or raw.get("gazette_number", ""),
            "president": info.get("Presidente", ""),
            "consultor": info.get("Consultor", ""),
            "observation": info.get("Observacion", ""),
            "url": f"{FILE_URL}?documentId={doc_id}&managementType=1",
        }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="DO/ConsultoriaJuridica scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    parser.add_argument("--full", action="store_true", help="Full bootstrap")
    args = parser.parse_args()

    source_dir = Path(__file__).resolve().parent
    scraper = ConsultoriaJuridicaScraper(str(source_dir))

    if args.command == "test":
        logger.info("Testing connectivity...")
        token = scraper._get_token()
        logger.info(f"Got CSRF token: {token[:20]}...")
        rows = scraper._search_year(2024)
        logger.info(f"Search 2024: {len(rows)} results")
        if rows:
            doc = rows[0]
            info = scraper._get_doc_info(doc["document_id"])
            logger.info(f"DocumentInfo: {json.dumps(info, indent=2, ensure_ascii=False)[:300]}")
            pdf = scraper._download_pdf(doc["document_id"])
            if pdf:
                text = _extract_text_from_pdf(pdf)
                logger.info(f"PDF text: {len(text)} chars — {text[:200]}")
        logger.info("Test passed!")
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample = args.sample and not args.full
        result = scraper.bootstrap(sample_mode=sample, sample_size=15)
        logger.info(f"Bootstrap result: {json.dumps(result, indent=2)}")
    elif args.command == "update":
        result = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
