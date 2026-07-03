#!/usr/bin/env python3
"""
INTL/SADC-LegalInstruments -- SADC Treaties, Protocols & Legal Instruments

Fetches legal instruments from the Southern African Development Community
(SADC) website at sadc.int:
  - Protocols (~25 English across 3 pages)
  - Declarations (~15 English)
  - Charters (3)
  - Pacts (3)
  - Regional Codes & Policies (~19)
  - SADC Treaty & amendments (~10 English)

Strategy:
  - Scrape category listing pages to collect document slugs
  - Visit each /document/{slug} detail page for PDF URL + metadata
  - Download PDFs and extract text via pdfplumber
  - Filter English documents only (avoid FR/PT duplicates)
  - Many older PDFs are scanned images; only text-based PDFs yield full text

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap --full     # Full fetch
  python bootstrap.py bootstrap-fast       # Alias for --full
"""

import io
import re
import sys
import json
import time
import logging
import hashlib
from html import unescape
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.SADC-LegalInstruments")

SOURCE_ID = "INTL/SADC-LegalInstruments"
BASE_URL = "https://www.sadc.int"

# Category pages: (path, max_pages, instrument_type)
# Ordered by likelihood of having text-based PDFs (newer first)
CATEGORIES = [
    ("/sadc-protocols", 3, "protocol"),
    ("/regional-codes-policies", 1, "regional_code"),
    ("/declarations", 2, "declaration"),
    ("/charters", 1, "charter"),
    ("/pacts", 1, "pact"),
    ("/sadc-treaty", 1, "treaty"),
]

MAX_PDF_SIZE = 15 * 1024 * 1024  # 15 MB
REQUEST_DELAY = 3  # seconds between requests to avoid drops

# Skip non-English documents
NON_ENGLISH_PATTERNS = [
    r"/pt-pt/", r"/fr/",
    r"-portuguese$", r"-french$",
    r"-portugues[ea]?$", r"-francais[ea]?$",
    r"protocolo-sobre", r"protocole-sur",
    r"secretario-executivo", r"secretaire-executif",
    r"plano-institucional", r"plan-dactivites",
    r"plano-director", r"plan-directeur",
]

# Generic SADC description that appears on many pages (not real content)
GENERIC_DESC_FRAGMENT = "achieve development, peace and security, and economic growth"


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities, preserving paragraph breaks."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


def is_non_english(slug: str) -> bool:
    """Check if a document slug is for a non-English language version."""
    for pattern in NON_ENGLISH_PATTERNS:
        if re.search(pattern, slug, re.IGNORECASE):
            return True
    return False


def _create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
        "Accept": "text/html,application/xhtml+xml,application/pdf",
    })
    return session


class SADCLegalScraper(BaseScraper):
    """Scraper for INTL/SADC-LegalInstruments."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = _create_session()

    def _get(self, url: str, timeout: int = 30) -> Optional[requests.Response]:
        """Fetch a URL with retry on connection drops."""
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                wait = (attempt + 1) * 10
                logger.warning(f"Connection error (attempt {attempt+1}/3), waiting {wait}s: {e}")
                time.sleep(wait)
                self.session = _create_session()
            except requests.HTTPError as e:
                logger.error(f"HTTP error for {url}: {e}")
                return None
        logger.error(f"Failed after 3 attempts: {url}")
        return None

    def _get_page(self, url: str) -> Optional[str]:
        """Fetch an HTML page."""
        resp = self._get(url)
        return resp.text if resp else None

    def _extract_doc_slugs(self, html: str) -> list[str]:
        """Extract /document/{slug} links from a category listing page."""
        slugs = re.findall(r'href="(/document/[^"]+)"', html)
        seen = set()
        unique = []
        for s in slugs:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    def _extract_detail(self, slug: str) -> Optional[dict]:
        """Visit a document detail page and extract metadata + PDF URL."""
        url = f"{BASE_URL}{slug}"
        html = self._get_page(url)
        if not html:
            return None

        # Title from <h1>
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else slug.split("/")[-1].replace("-", " ").title()

        # Body description (specific to document, not generic sidebar)
        body_match = re.search(
            r'field--name-body.*?field__item">\s*(.*?)\s*</div>',
            html, re.DOTALL
        )
        description = ""
        if body_match:
            raw_desc = strip_html(body_match.group(1))
            # Skip generic SADC description that appears on all pages
            if GENERIC_DESC_FRAGMENT not in raw_desc and len(raw_desc) > 500:
                description = raw_desc

        # Date signed
        date = None
        date_match = re.search(r'field--name-field-date-signed.*?datetime="([^"]+)"', html, re.DOTALL)
        if date_match:
            try:
                dt = datetime.fromisoformat(date_match.group(1).replace("Z", "+00:00"))
                date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # PDF URL
        pdf_links = re.findall(r'href="(/sites/default/files/[^"]+\.pdf)"', html)
        pdf_url = f"{BASE_URL}{pdf_links[0]}" if pdf_links else None

        return {
            "title": unescape(title),
            "description": description,
            "date": date,
            "pdf_url": pdf_url,
            "page_url": url,
        }

    def _extract_pdf_text(self, url: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        if not HAS_PDFPLUMBER:
            logger.warning("pdfplumber not available, cannot extract PDF text")
            return None

        resp = self._get(url, timeout=90)
        if not resp:
            return None

        if len(resp.content) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({len(resp.content)} bytes): {url}")
            return None

        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass

                text = "\n\n".join(pages_text)
                if len(text) < 100:
                    logger.warning(f"PDF text too short ({len(text)} chars, likely scanned): {url}")
                    return None
                return text

        except Exception as e:
            logger.error(f"PDF extraction failed for {url}: {e}")
            return None

    def _make_id(self, title: str, instrument_type: str) -> str:
        """Generate a stable ID from title."""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return f"sadc-{instrument_type}-{slug}"[:120]

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all SADC legal instruments."""
        count = 0
        seen_titles = set()
        skipped_scanned = 0

        for cat_path, max_pages, instrument_type in CATEGORIES:
            logger.info(f"=== Category: {cat_path} ({instrument_type}) ===")

            all_slugs = []
            for page_num in range(max_pages):
                page_url = f"{BASE_URL}{cat_path}?items_per_page=50"
                if page_num > 0:
                    page_url += f"&page={page_num}"

                html = self._get_page(page_url)
                if not html:
                    break

                slugs = self._extract_doc_slugs(html)
                if not slugs:
                    break

                all_slugs.extend(slugs)
                logger.info(f"  Page {page_num}: {len(slugs)} document links")
                time.sleep(REQUEST_DELAY)

            # Filter English-only
            english_slugs = [s for s in all_slugs if not is_non_english(s)]
            logger.info(f"  Total: {len(all_slugs)} slugs, {len(english_slugs)} English")

            for slug in english_slugs:
                if sample and count >= 15:
                    return

                time.sleep(REQUEST_DELAY)
                detail = self._extract_detail(slug)
                if not detail:
                    logger.warning(f"  Skipping (no detail): {slug}")
                    continue

                # Dedup by title
                title_key = detail["title"].lower().strip()
                if title_key in seen_titles:
                    logger.info(f"  Skipping duplicate: {detail['title'][:50]}")
                    continue
                seen_titles.add(title_key)

                # Extract PDF text
                text = None
                if detail["pdf_url"]:
                    logger.info(f"  Fetching PDF: {detail['title'][:60]}...")
                    time.sleep(REQUEST_DELAY)
                    text = self._extract_pdf_text(detail["pdf_url"])

                if not text:
                    # Use description only if it's real content (not generic)
                    if detail["description"]:
                        text = detail["description"]
                        logger.info(f"  Using body text ({len(text)} chars)")
                    else:
                        skipped_scanned += 1
                        logger.warning(f"  Skipping (scanned PDF, no text): {detail['title'][:50]}")
                        continue

                doc_id = self._make_id(detail["title"], instrument_type)

                record = {
                    "_id": doc_id,
                    "_source": SOURCE_ID,
                    "_type": "legislation",
                    "_fetched_at": datetime.now(timezone.utc).isoformat(),
                    "title": detail["title"],
                    "text": text,
                    "date": detail["date"],
                    "url": detail["page_url"],
                    "instrument_type": instrument_type,
                }

                yield record
                count += 1
                logger.info(f"  [{count}] {detail['title'][:50]} ({len(text)} chars)")

        logger.info(f"Completed: {count} records, {skipped_scanned} skipped (scanned PDFs)")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """SADC documents are rarely updated; full refresh is preferred."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Records are already normalized during fetch."""
        return raw


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/SADC-LegalInstruments bootstrap")
    subparsers = parser.add_subparsers(dest="command")

    boot_parser = subparsers.add_parser("bootstrap")
    boot_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot_parser.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast")

    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample = getattr(args, "sample", False) and args.command != "bootstrap-fast"
        full = getattr(args, "full", False) or args.command == "bootstrap-fast"

        scraper = SADCLegalScraper()
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        records = []
        for record in scraper.fetch_all(sample=not full):
            records.append(record)
            fname = re.sub(r"[^a-z0-9_-]", "_", record["_id"][:60]) + ".json"
            out_path = sample_dir / fname
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(records)} records to {sample_dir}")

        texts = [r for r in records if r.get("text") and len(r["text"]) > 100]
        if texts:
            avg_len = sum(len(r["text"]) for r in texts) // len(texts)
            logger.info(f"Records with text: {len(texts)}/{len(records)}, avg {avg_len} chars")
        else:
            logger.warning("No records with substantial text content!")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
