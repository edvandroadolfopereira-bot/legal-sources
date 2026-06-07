#!/usr/bin/env python3
"""
LB/CMA — Lebanon Capital Markets Authority

Fetches laws, decisions, implementing regulations, and announcements
from the CMA website (cma.gov.lb).

Strategy:
  1. Fetch the /laws-and-regulations/ page
  2. Parse the 4 HTML tables (laws, decisions, regulations, announcements)
     to extract PDF URLs and metadata
  3. Download each PDF and extract full text via pdfplumber

Data:
  - ~154 documents (8 laws, 38 decisions, 8 regulation series, 100 announcements)
  - Languages: Arabic and English
  - Period: 2000-2026

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import requests

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.cma.gov.lb"
SOURCE_ID = "LB/CMA"
SAMPLE_DIR = Path(__file__).parent / "sample"
REQUEST_DELAY = 2.0


# ── HTML parser ───────────────────────────────────────────────────

class _PageParser(HTMLParser):
    """Parse the laws-and-regulations page to extract PDF links with metadata."""

    def __init__(self):
        super().__init__()
        self.documents: List[Dict[str, str]] = []
        self._in_table = False
        self._current_table_id: Optional[str] = None
        self._in_row = False
        self._in_cell = False
        self._in_thead = False
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self._cell_hrefs: List[str] = []
        self._table_category_map = {
            "law": "law",
            "decisions": "decision",
            "series": "regulation",
            "announcement": "announcement",
        }

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self._in_table = True
            tid = attrs_dict.get("id", "")
            self._current_table_id = tid
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tbody":
            self._in_thead = False
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in ("td", "th") and self._in_row:
            self._in_cell = True
            self._current_cell = []
            self._cell_hrefs = []
        elif tag == "a" and self._in_cell:
            href = attrs_dict.get("href", "")
            if href and (".pdf" in href.lower() or "wp-content" in href.lower()):
                if not href.startswith("http"):
                    href = urljoin(BASE_URL, href)
                self._cell_hrefs.append(href)

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
            self._current_table_id = None
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if not self._in_thead and self._current_row and self._current_table_id:
                self._process_row(self._current_table_id, self._current_row)
        elif tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            cell_text = "".join(self._current_cell).strip()
            # Store cell text; append PDF URLs as a special marker
            if self._cell_hrefs:
                cell_text = "|||".join(self._cell_hrefs)
            self._current_row.append(cell_text)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)

    def _process_row(self, table_id: str, row: List[str]):
        """Process a table row based on which table it belongs to."""
        # Determine category from table ID
        category = None
        for key, cat in self._table_category_map.items():
            if key in table_id.lower():
                category = cat
                break
        if not category:
            return

        # Find PDF URLs in row cells
        pdf_urls = []
        for cell in row:
            if "|||" in cell:
                pdf_urls.extend(cell.split("|||"))
            elif cell.startswith("http") and ".pdf" in cell.lower():
                pdf_urls.append(cell)

        if not pdf_urls:
            return

        # Extract metadata from row
        # Typical structure: #, Date, Title/Subject, Language links
        number = ""
        date_str = ""
        title = ""

        text_cells = [c for c in row if "|||" not in c and not c.startswith("http")]

        if len(text_cells) >= 1:
            number = text_cells[0].strip()
        if len(text_cells) >= 2:
            date_str = text_cells[1].strip()
        if len(text_cells) >= 3:
            title = text_cells[2].strip()
        if not title and len(text_cells) >= 2:
            title = text_cells[1].strip()

        for pdf_url in pdf_urls:
            doc = {
                "category": category,
                "number": number,
                "date": date_str,
                "title": title,
                "pdf_url": pdf_url.strip(),
            }
            self.documents.append(doc)


def parse_laws_page(html: str) -> List[Dict[str, str]]:
    """Parse the laws-and-regulations page into document metadata."""
    parser = _PageParser()
    parser.feed(html)

    # Deduplicate by PDF URL (prefer English versions when both exist)
    seen_urls = set()
    unique_docs = []
    for doc in parser.documents:
        url = doc["pdf_url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique_docs.append(doc)

    return unique_docs


# ── Fallback: scrape decision posts ──────────────────────────────

class _DecisionPostParser(HTMLParser):
    """Parse the CMA decisions archive page for individual post links."""

    def __init__(self):
        super().__init__()
        self.post_urls: List[Dict[str, str]] = []
        self._in_article = False
        self._in_title = False
        self._current_url = ""
        self._current_title: List[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if tag == "article":
            self._in_article = True
        elif tag == "h2" and "entry-title" in cls:
            self._in_title = True
            self._current_title = []
        elif tag == "a" and self._in_title:
            self._current_url = attrs_dict.get("href", "")

    def handle_endtag(self, tag):
        if tag == "article":
            self._in_article = False
        elif tag == "h2" and self._in_title:
            self._in_title = False
            title = "".join(self._current_title).strip()
            if self._current_url and title:
                self.post_urls.append({
                    "url": self._current_url,
                    "title": title,
                })
            self._current_url = ""

    def handle_data(self, data):
        if self._in_title:
            self._current_title.append(data)


# ── PDF extraction ─────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    if not HAS_PDF:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return ""


# ── Fetching ───────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal research; open data)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def _parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to ISO 8601."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try to extract year at minimum
    m = re.search(r"(\d{4})", date_str)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def _detect_lang(pdf_url: str) -> str:
    """Detect language from PDF URL."""
    lower = pdf_url.lower()
    if "english" in lower or "englsih" in lower or "-en." in lower or "_en." in lower or "-EN." in pdf_url:
        return "en"
    if "arabic" in lower or "عربي" in lower:
        return "ar"
    # Check for Arabic characters in URL-decoded filename
    from urllib.parse import unquote
    decoded = unquote(pdf_url)
    if any('\u0600' <= c <= '\u06FF' for c in decoded):
        return "ar"
    return "en"


def _make_id(category: str, number: str, pdf_url: str) -> str:
    """Generate a unique document ID."""
    lang = _detect_lang(pdf_url)
    # Clean "# " prefix from number
    clean_number = re.sub(r'^#\s*', '', number).strip() if number else ""
    if clean_number:
        clean_num = re.sub(r'[^\w\-.]', '-', clean_number)
        return f"CMA-{category}-{clean_num}-{lang}"
    # Fallback: use filename from URL
    from urllib.parse import unquote
    filename = unquote(pdf_url.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    clean_name = re.sub(r'[^\w\-.]', '-', filename)[:60]
    return f"CMA-{category}-{clean_name}-{lang}"


# ── Normalize ──────────────────────────────────────────────────────

def _clean_field(value: str, prefixes: List[str]) -> str:
    """Remove known header text prefixes from field values."""
    for p in prefixes:
        if value.startswith(p):
            value = value[len(p):]
    return value.strip()


def normalize(doc: Dict[str, str], pdf_text: str) -> Dict[str, Any]:
    """Normalize a document record into standard schema."""
    category = doc["category"]
    number = _clean_field(doc.get("number", ""), ["# ", "#"])
    title = _clean_field(doc.get("title", ""),
                         ["Law Title\n", "Decision Title\n", "Regulation Title\n",
                          "Announcement Title\n", "Title\n", "Subject\n"])
    date_str = _clean_field(doc.get("date", ""), ["Date ", "التاريخ "])
    pdf_url = doc["pdf_url"]

    doc_id = _make_id(category, number, pdf_url)
    iso_date = _parse_date(date_str)

    # Build title if missing
    if not title:
        title = f"CMA {category.title()} No. {number}" if number else f"CMA {category.title()}"

    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": pdf_text,
        "date": iso_date,
        "url": pdf_url,
        "category": category,
        "document_number": number,
    }


# ── Bootstrap ──────────────────────────────────────────────────────

def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all CMA documents with full text."""
    if not HAS_PDF:
        logger.error("pdfplumber not available — cannot extract PDF text")
        sys.exit(1)

    session = _session()

    # Fetch the main laws page
    logger.info("Fetching laws-and-regulations page...")
    try:
        resp = session.get(f"{BASE_URL}/laws-and-regulations/", timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch laws page: %s", e)
        sys.exit(1)

    documents = parse_laws_page(resp.text)
    logger.info("Found %d documents from laws-and-regulations page", len(documents))

    if not documents:
        logger.error("No documents parsed from page")
        sys.exit(1)

    limit = 15 if sample else len(documents)
    success = 0
    errors = 0

    for i, doc in enumerate(documents[:limit]):
        pdf_url = doc["pdf_url"]
        logger.info("[%d/%d] Fetching %s %s: %s",
                    i + 1, min(limit, len(documents)),
                    doc["category"], doc.get("number", ""),
                    pdf_url[-60:])

        try:
            resp = session.get(pdf_url, timeout=60)
            if resp.status_code != 200:
                logger.warning("PDF %s returned %d", pdf_url, resp.status_code)
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not pdf_url.lower().endswith(".pdf"):
                logger.warning("Not a PDF: %s (Content-Type: %s)", pdf_url, content_type)
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            pdf_text = extract_pdf_text(resp.content)
            if not pdf_text or len(pdf_text) < 50:
                logger.warning("Insufficient text from %s (%d chars)",
                               pdf_url, len(pdf_text) if pdf_text else 0)
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            record = normalize(doc, pdf_text)
            success += 1
            yield record

        except Exception as e:
            logger.error("Error fetching %s: %s", pdf_url, e)
            errors += 1

        time.sleep(REQUEST_DELAY)

    logger.info("Done: %d success, %d errors out of %d attempted",
                success, errors, min(limit, len(documents)))


def main():
    parser = argparse.ArgumentParser(description="LB/CMA bootstrap")
    sub = parser.add_subparsers(dest="command")
    boot = sub.add_parser("bootstrap", help="Fetch CMA documents")
    boot.add_argument("--sample", action="store_true", help="Fetch 15 sample records")
    args = parser.parse_args()

    if args.command != "bootstrap":
        parser.print_help()
        sys.exit(1)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for record in fetch_all(sample=args.sample):
        out = SAMPLE_DIR / f"{record['_id']}.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        count += 1
        text_len = len(record.get("text", ""))
        logger.info("Saved %s (%d chars text)", record["_id"], text_len)

    logger.info("Total records saved: %d", count)
    if count == 0:
        logger.error("No records fetched — check connectivity and PDF access")
        sys.exit(1)


if __name__ == "__main__":
    main()
