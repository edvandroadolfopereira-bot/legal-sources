#!/usr/bin/env python3
"""
YE/MOJ -- Yemen Ministry of Justice Legislation Database

Fetches laws and regulations from the Yemen Ministry of Justice website.
Laws are listed as HTML table entries with PDF download links.

Approach:
  1. Scrape list pages at /LawsM?page={N} (5 pages, 8 items each)
  2. Extract title and PDF link for each law
  3. Download PDF and extract text with pdfplumber (fallback: PyPDF2)

Data:
  - ~38 laws (presidential decrees, legislation, regulations)
  - Full text extracted from PDFs
  - Arabic language

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import io
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.YE.MOJ")

BASE_URL = "https://www.moj.gov.ye"
LIST_URL = "/LawsM"
TOTAL_PAGES = 5

# Try to import PDF libraries
try:
    import pdfplumber
    PDF_LIB = "pdfplumber"
except ImportError:
    pdfplumber = None
    PDF_LIB = None

if PDF_LIB is None:
    try:
        from PyPDF2 import PdfReader
        PDF_LIB = "PyPDF2"
    except ImportError:
        PdfReader = None

if PDF_LIB is None:
    try:
        import fitz  # PyMuPDF
        PDF_LIB = "PyMuPDF"
    except ImportError:
        fitz = None

if PDF_LIB is None:
    logger.error("No PDF library available (pdfplumber, PyPDF2, or PyMuPDF required)")
    sys.exit(1)

logger.info(f"Using PDF library: {PDF_LIB}")


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using the available library."""
    if PDF_LIB == "pdfplumber":
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
            return "\n".join(parts)
    elif PDF_LIB == "PyPDF2":
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)
    elif PDF_LIB == "PyMuPDF":
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parts = []
        for page in doc:
            t = page.get_text()
            if t:
                parts.append(t)
        doc.close()
        return "\n".join(parts)
    return ""


def parse_year_from_title(title: str) -> Optional[str]:
    """Extract year from Arabic law title (e.g., 'لسنة 2012م')."""
    match = re.search(r'لسنة\s*(\d{4})', title)
    if match:
        return match.group(1)
    match = re.search(r'(\d{4})\s*م', title)
    if match:
        return match.group(1)
    return None


class YEMOJScraper(BaseScraper):
    """Scraper for YE/MOJ -- Yemen Ministry of Justice Legislation."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=120,
        )

    def _parse_list_page(self, page: int) -> list:
        """Parse a list page and return law entries."""
        from bs4 import BeautifulSoup

        url = f"/Home/LawsM?page={page}" if page > 1 else LIST_URL
        self.rate_limiter.wait()
        resp = self.client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="table_id")
        if not table:
            return []

        entries = []
        for row in table.select("tbody tr"):
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            seq = tds[0].get_text(strip=True)
            title = tds[1].get_text(strip=True)
            downloads = tds[2].get_text(strip=True)
            link_a = tds[3].find("a", href=True)
            if not link_a:
                continue
            pdf_path = link_a["href"]
            entries.append({
                "seq": seq,
                "title": title,
                "downloads": downloads,
                "pdf_path": pdf_path,
            })
        return entries

    def _download_pdf_text(self, pdf_path: str) -> str:
        """Download a PDF and extract text."""
        self.rate_limiter.wait()
        resp = self.client.get(pdf_path)
        resp.raise_for_status()

        if not resp.content or len(resp.content) < 100:
            return ""

        try:
            return extract_text_from_pdf(resp.content)
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_path}: {e}")
            return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        law_id = raw.get("pdf_path", "").replace("/LawsMD/", "")
        title = raw.get("title", "")
        text = raw.get("text", "")
        year = parse_year_from_title(title)
        date = f"{year}-01-01" if year else None

        return {
            "_id": f"YE/MOJ/{law_id}",
            "_source": "YE/MOJ",
            "_type": "legislation",
            "_fetched_at": now,
            "title": title,
            "text": text,
            "date": date,
            "url": f"{BASE_URL}/LawsMD/{law_id}",
            "doc_id": law_id,
            "year": year,
            "downloads": raw.get("downloads", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        limit = 12 if sample else None
        count = 0

        for page in range(1, TOTAL_PAGES + 1):
            if limit and count >= limit:
                break

            logger.info(f"Fetching list page {page}/{TOTAL_PAGES}...")
            try:
                entries = self._parse_list_page(page)
            except Exception as e:
                logger.error(f"Failed to fetch list page {page}: {e}")
                break

            logger.info(f"  Found {len(entries)} entries")

            for entry in entries:
                if limit and count >= limit:
                    break

                title = entry["title"]
                if not title:
                    logger.warning(f"  Skipping entry with empty title")
                    continue

                logger.info(f"  [{count + 1}] Downloading PDF for: {title[:60]}...")
                try:
                    text = self._download_pdf_text(entry["pdf_path"])
                except Exception as e:
                    logger.error(f"  Failed to download PDF: {e}")
                    continue

                if len(text) < 50:
                    logger.warning(f"  Skipping - extracted text too short ({len(text)} chars)")
                    continue

                entry["text"] = text
                yield entry
                count += 1
                logger.info(f"  [{count}] OK: {len(text)} chars extracted")

        logger.info(f"Fetched {count} laws total")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(sample=False)


if __name__ == "__main__":
    scraper = YEMOJScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test":
        scraper.test_connection()
    elif command == "bootstrap":
        scraper.bootstrap(sample_mode=sample_mode)
    elif command == "update":
        scraper.bootstrap(sample_mode=False)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
