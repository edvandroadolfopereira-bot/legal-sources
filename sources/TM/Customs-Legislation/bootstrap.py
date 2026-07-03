#!/usr/bin/env python3
"""
TM/Customs-Legislation — Turkmenistan State Customs Service

Fetches customs legislation from customs.gov.tm:
  - Customs Code (full text from HTML + PDF in EN/RU/TM)
  - Law on Customs Service (HTML in TK + RU)
  - 6 Regulatory orders (HTML summaries)
  - Customs duties, fees, and excise schedules (HTML tables)

Strategy:
  1. Scrape defined pages from customs.gov.tm
  2. Extract text from HTML (strip tags, decode entities)
  3. For pages with PDF links, download and extract text via pdfplumber/PyPDF2
  4. Use the longer version (HTML vs PDF) as the document text

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
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
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from html import unescape
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.TM.Customs-Legislation")

SITE_BASE = "https://customs.gov.tm"
USER_AGENT = "LegalDataHunter/1.0 (legal research; open data collection)"

# Pages to scrape — each becomes one document
PAGES = [
    {
        "doc_id": "TM-customs-code-en",
        "url": "/en/pages/customs-code",
        "title": "Customs Code of Turkmenistan (English)",
        "lang": "en",
        "pdf_url": "https://customs.gov.tm/storage/posts/94/pdf/kodeks-s-izmeneniyami-en.pdf",
    },
    {
        "doc_id": "TM-customs-code-ru",
        "url": "/ru/pages/customs-code",
        "title": "Таможенный кодекс Туркменистана (Russian)",
        "lang": "ru",
        "pdf_url": "https://customs.gov.tm/storage/posts/94/pdf/kodeks-s-izmeneniyami-ru.pdf",
    },
    {
        "doc_id": "TM-customs-code-tm",
        "url": "/tk/pages/customs-code",
        "title": "Türkmenistanyň Gümrük kodeksi (Turkmen)",
        "lang": "tm",
        "pdf_url": "https://customs.gov.tm/storage/posts/94/pdf/kodeks-s-izmeneniyami-tm (1).pdf",
    },
    {
        "doc_id": "TM-customs-service-law-tk",
        "url": "/tk/pages/customs-laws",
        "title": "Türkmenistanyň Kanuny — Gümrük gullugy hakynda (Turkmen)",
        "lang": "tm",
    },
    {
        "doc_id": "TM-customs-service-law-ru",
        "url": "/ru/pages/customs-laws",
        "title": "Закон Туркменистана — О таможенной службе (Russian)",
        "lang": "ru",
    },
    {
        "doc_id": "TM-customs-duties",
        "url": "/en/customs-info/customs-fees/duties",
        "title": "Customs Duties — Import, Export, and Duty-Free Lists",
        "lang": "en",
    },
    {
        "doc_id": "TM-customs-fees",
        "url": "/en/customs-info/customs-fees/fees",
        "title": "Customs Fees of Turkmenistan",
        "lang": "en",
    },
    {
        "doc_id": "TM-excise-rates",
        "url": "/en/customs-info/customs-fees/excices",
        "title": "Excise Rates for Imported Goods",
        "lang": "en",
    },
    {
        "doc_id": "TM-commodity-codes",
        "url": "/en/customs-info/customs-fees/lists_of_codes",
        "title": "Commodity Nomenclature Codes — Classification Explanations",
        "lang": "en",
    },
]

# Regulatory orders from the customs-control page (each is a separate doc)
REGULATORY_ORDERS = [
    {
        "doc_id": "TM-reg-order-reprocessing-1999",
        "title": "Regulation on Customs Reprocessing Regime (Order No. 6, 1999)",
        "year": "1999",
    },
    {
        "doc_id": "TM-reg-order-destruction-2005",
        "title": "Regulation on Goods Destruction Customs Regime (2005)",
        "year": "2005",
    },
    {
        "doc_id": "TM-reg-order-state-benefit-2005",
        "title": "Regulation on Renunciation in Favour of the State Customs Regime (2005)",
        "year": "2005",
    },
    {
        "doc_id": "TM-reg-order-temp-storage-2009",
        "title": "Regulation on Temporary Storage of Goods under Customs Control (Order No. 15, 2009)",
        "year": "2009",
    },
    {
        "doc_id": "TM-reg-order-export-cert-2016",
        "title": "List of Products Requiring Certification upon Export (Presidential Decree No. 14594, 2016)",
        "year": "2016",
    },
    {
        "doc_id": "TM-reg-order-transport-decl-2020",
        "title": "Procedure for Filing Transport Entry and Exit Declarations (2020)",
        "year": "2020",
    },
]


def _clean_html(text: str) -> str:
    """Strip HTML tags and clean text."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:p|div|h[1-6]|li|tr|td|th)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\ufeff", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def _extract_page_text(html: str) -> str:
    """Extract main content text from a customs.gov.tm page."""
    # Try to find the main content area
    # The site uses Bootstrap; content is typically in a container after the nav
    # Look for the page-specific content block
    content = ""

    # Strategy 1: Find content between navigation and footer
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.S)
    if main_match:
        content = main_match.group(1)
    else:
        # Fallback: get body content
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.S)
        if body_match:
            content = body_match.group(1)

    if not content:
        return ""

    # Remove nav, header, footer, script, style elements
    for tag in ['nav', 'header', 'footer', 'script', 'style', 'noscript']:
        content = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', content, flags=re.S | re.I)

    # Extract text from tables (preserve structure)
    tables = re.findall(r'<table[^>]*>(.*?)</table>', content, re.S)
    table_text = ""
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)
            cell_texts = [_clean_html(c).strip() for c in cells]
            cell_texts = [c for c in cell_texts if c]
            if cell_texts:
                table_text += " | ".join(cell_texts) + "\n"
        table_text += "\n"

    # Extract paragraph/heading text
    paragraphs = re.findall(r'<(?:p|h[1-6]|li)[^>]*>(.*?)</(?:p|h[1-6]|li)>', content, re.S)
    para_text = "\n\n".join(_clean_html(p) for p in paragraphs if _clean_html(p))

    # Combine
    full_text = para_text
    if table_text.strip():
        full_text += "\n\n" + table_text.strip()

    return full_text.strip()


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber or PyPDF2."""
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


class CustomsLegislationScraper(BaseScraper):
    """Scraper for Turkmenistan State Customs Service legislation."""

    def __init__(self, source_dir: str = None):
        if source_dir is None:
            source_dir = str(Path(__file__).parent)
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _fetch_page(self, path: str) -> str:
        """Fetch an HTML page from customs.gov.tm."""
        url = SITE_BASE + path
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Fetch attempt {attempt+1} failed for {url}: {e}")
                    time.sleep(2 * (attempt + 1))
                else:
                    logger.error(f"Failed to fetch {url} after 3 attempts: {e}")
                    return ""

    def _fetch_pdf(self, url: str) -> Optional[bytes]:
        """Download a PDF."""
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                if len(resp.content) < 100:
                    return None
                return resp.content
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"PDF download attempt {attempt+1} failed: {e}")
                    time.sleep(2 * (attempt + 1))
                else:
                    logger.error(f"PDF download failed: {url}")
                    return None

    def _scrape_page(self, page_def: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Scrape a single page and return a raw record."""
        logger.info(f"Scraping: {page_def['title']}")
        time.sleep(2)

        html = self._fetch_page(page_def["url"])
        if not html:
            logger.warning(f"Empty response for {page_def['url']}")
            return None

        html_text = _extract_page_text(html)
        logger.info(f"  HTML text: {len(html_text)} chars")

        # Try PDF if available
        pdf_text = ""
        pdf_url = page_def.get("pdf_url")
        if pdf_url:
            logger.info(f"  Downloading PDF: {pdf_url}")
            time.sleep(2)
            pdf_bytes = self._fetch_pdf(pdf_url)
            if pdf_bytes:
                pdf_text = _extract_pdf_text(pdf_bytes)
                logger.info(f"  PDF text: {len(pdf_text)} chars")

        # Use the longer version
        text = pdf_text if len(pdf_text) > len(html_text) else html_text

        if not text or len(text) < 50:
            logger.warning(f"  Insufficient text for {page_def['doc_id']}: {len(text)} chars")
            return None

        return {
            "doc_id": page_def["doc_id"],
            "title": page_def["title"],
            "text": text,
            "url": SITE_BASE + page_def["url"],
            "lang": page_def.get("lang", "en"),
            "pdf_url": pdf_url,
        }

    def _scrape_regulatory_orders(self) -> List[Dict[str, Any]]:
        """Scrape the regulatory orders listing page."""
        logger.info("Scraping regulatory orders page")
        time.sleep(2)
        html = self._fetch_page("/en/customs-info/customs-control")
        if not html:
            return []

        # Extract p tags from main content
        main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.S)
        content = main_match.group(1) if main_match else html

        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.S)
        cleaned = [_clean_html(p) for p in paragraphs]
        cleaned = [c for c in cleaned if c and len(c) > 10]

        # Pair up: title + description
        orders = []
        for i in range(0, len(cleaned) - 1, 2):
            title_text = cleaned[i]
            desc_text = cleaned[i + 1] if i + 1 < len(cleaned) else ""
            order_idx = i // 2
            if order_idx < len(REGULATORY_ORDERS):
                order_def = REGULATORY_ORDERS[order_idx]
                full_text = f"{title_text}\n\n{desc_text}"
                orders.append({
                    "doc_id": order_def["doc_id"],
                    "title": order_def["title"],
                    "text": full_text,
                    "url": SITE_BASE + "/en/customs-info/customs-control",
                    "lang": "tm",
                    "date": order_def.get("year"),
                })
                logger.info(f"  Order {order_idx}: {len(full_text)} chars")

        return orders

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Yield all documents."""
        # Scrape defined pages
        for page_def in PAGES:
            record = self._scrape_page(page_def)
            if record:
                yield record

        # Scrape regulatory orders
        orders = self._scrape_regulatory_orders()
        for order in orders:
            yield order

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        """Yield all (static site, no incremental updates)."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform raw record into standard schema."""
        text = raw.get("text", "")
        if not text or len(text) < 50:
            return None

        doc_id = raw["doc_id"]
        date_str = raw.get("date")

        return {
            "_id": doc_id,
            "_source": "TM/Customs-Legislation",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": text,
            "date": date_str,
            "url": raw["url"],
            "language": raw.get("lang", "en"),
            "pdf_url": raw.get("pdf_url"),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="TM/Customs-Legislation bootstrap")
    subparsers = parser.add_subparsers(dest="command")

    boot_parser = subparsers.add_parser("bootstrap", help="Bootstrap data")
    boot_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot_parser.add_argument("--full", action="store_true", help="Full bootstrap")

    subparsers.add_parser("bootstrap-fast", help="Alias for bootstrap --full")
    subparsers.add_parser("test", help="Test connectivity")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = CustomsLegislationScraper()

    if args.command == "test":
        logger.info("Testing connectivity to customs.gov.tm...")
        try:
            resp = scraper.session.get(SITE_BASE + "/en", timeout=15)
            resp.raise_for_status()
            logger.info(f"OK — status {resp.status_code}, {len(resp.text)} bytes")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            sys.exit(1)
        return

    is_sample = args.command == "bootstrap" and args.sample
    is_full = args.command in ("bootstrap-fast",) or (args.command == "bootstrap" and args.full)

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    total_chars = 0
    for raw in scraper.fetch_all():
        record = scraper.normalize(raw)
        if not record:
            continue
        count += 1
        text_len = len(record.get("text", ""))
        total_chars += text_len
        logger.info(f"[{count}] {record['_id']}: {record['title'][:60]} ({text_len} chars)")

        # Save sample
        safe_id = record["_id"].replace("/", "_").replace(" ", "_")
        sample_path = sample_dir / f"{safe_id}.json"
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        if is_sample and count >= 15:
            break

    logger.info(f"Done: {count} records, {total_chars} total chars, avg {total_chars // max(count,1)} chars/record")


if __name__ == "__main__":
    main()
