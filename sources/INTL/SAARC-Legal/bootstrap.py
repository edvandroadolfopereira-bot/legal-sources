#!/usr/bin/env python3
"""
INTL/SAARC-Legal -- SAARC Conventions, Agreements & Summit Declarations

Fetches legal instruments from the South Asian Association for Regional
Cooperation (SAARC) via the saarc-sec.org CMS JSON API:
  - Agreements & Conventions (28 instruments)
  - Summit Declarations (17 declarations, summits 1-18)
  - SAARC Charter (inline HTML text)

Strategy:
  - Fetch /api/pages/{slug} for each section
  - Parse HTML content to extract PDF links and metadata
  - Download PDFs and extract text via pdfplumber
  - Charter is embedded as HTML text, extracted directly

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

import requests

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
logger = logging.getLogger("legal-data-hunter.INTL.SAARC-Legal")

SOURCE_ID = "INTL/SAARC-Legal"
BASE_URL = "https://www.saarc-sec.org"
API_BASE = f"{BASE_URL}/api/pages"

# Pages to scrape
PAGES = [
    {"slug": "agreements-conventions", "instrument_type": "agreement"},
    {"slug": "summit-declarations", "instrument_type": "declaration"},
]

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB


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


class SAARCLegalScraper(BaseScraper):
    """Scraper for INTL/SAARC-Legal."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "application/json, text/html",
        })

    def _fetch_page(self, slug: str) -> Optional[dict]:
        """Fetch a CMS page via the JSON API."""
        url = f"{API_BASE}/{slug}"
        logger.info(f"Fetching page: {url}")
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch page {slug}: {e}")
            return None

    def _extract_pdf_links(self, html: str) -> list[dict]:
        """Extract PDF document links from HTML content."""
        docs = []
        seen = set()

        # Pattern: data-id="N" data-title="..." href="/medias/....pdf"
        pattern = r'data-id="(\d+)"[^>]*data-title="([^"]+)"[^>]*href="(/medias/[^"]+\.pdf)"'
        matches = re.findall(pattern, html)

        for doc_id, title, pdf_path in matches:
            key = (doc_id, title)
            if key in seen:
                continue
            seen.add(key)
            docs.append({
                "id": doc_id,
                "title": title.strip(),
                "pdf_url": f"{BASE_URL}{pdf_path}",
            })

        # Also capture links without data-id/data-title (fallback)
        if not docs:
            fallback = re.findall(r'href="(/medias/[^"]+\.pdf)"[^>]*title="([^"]+)"', html)
            for pdf_path, title in fallback:
                key = title.strip()
                if key not in seen:
                    seen.add(key)
                    docs.append({
                        "id": hashlib.md5(key.encode()).hexdigest()[:8],
                        "title": key,
                        "pdf_url": f"{BASE_URL}{pdf_path}",
                    })

        return docs

    def _extract_pdf_text(self, url: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        if not HAS_PDFPLUMBER:
            logger.warning("pdfplumber not available, cannot extract PDF text")
            return None

        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()

            if len(resp.content) > MAX_PDF_SIZE:
                logger.warning(f"PDF too large ({len(resp.content)} bytes): {url}")
                return None

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
                if len(text) < 50:
                    logger.warning(f"PDF text too short ({len(text)} chars): {url}")
                    return None
                return text

        except Exception as e:
            logger.error(f"PDF extraction failed for {url}: {e}")
            return None

    def _extract_charter_text(self) -> Optional[dict]:
        """Extract the SAARC Charter text from its page (inline HTML)."""
        data = self._fetch_page("saarc-charter")
        if not data or "page" not in data:
            return None

        html = data["page"]["content"].get("en", "")
        if not html:
            return None

        text = strip_html(html)
        if len(text) < 100:
            return None

        return {
            "_id": "SAARC-Charter",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": "Charter of the South Asian Association for Regional Cooperation",
            "text": text,
            "date": "1985-12-08",
            "url": f"{BASE_URL}/pages/saarc-charter",
            "instrument_type": "charter",
        }

    def _normalize_title(self, title: str) -> str:
        """Clean up title: remove '.pdf' suffix, fix spacing."""
        title = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE)
        title = title.strip()
        return title

    def _make_id(self, title: str, instrument_type: str) -> str:
        """Generate a stable ID from title."""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return f"saarc-{instrument_type}-{slug}"[:120]

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all SAARC legal instruments."""
        count = 0

        # 1. Fetch the SAARC Charter (inline text)
        logger.info("Fetching SAARC Charter...")
        charter = self._extract_charter_text()
        if charter:
            yield charter
            count += 1
            logger.info(f"Charter: {len(charter['text'])} chars")

        if sample and count >= 15:
            return

        # 2. Fetch each page category (agreements, declarations)
        for page_info in PAGES:
            slug = page_info["slug"]
            instrument_type = page_info["instrument_type"]

            data = self._fetch_page(slug)
            if not data or "page" not in data:
                logger.error(f"Could not fetch page: {slug}")
                continue

            html = data["page"]["content"].get("en", "")
            docs = self._extract_pdf_links(html)
            logger.info(f"Page '{slug}': found {len(docs)} PDF documents")

            for doc in docs:
                if sample and count >= 15:
                    return

                title = self._normalize_title(doc["title"])
                pdf_url = doc["pdf_url"]

                logger.info(f"  Fetching PDF: {title[:60]}...")
                time.sleep(2)  # Rate limiting

                text = self._extract_pdf_text(pdf_url)
                if not text:
                    logger.warning(f"  Skipping (no text): {title}")
                    continue

                doc_id = self._make_id(title, instrument_type)

                record = {
                    "_id": doc_id,
                    "_source": SOURCE_ID,
                    "_type": "legislation",
                    "_fetched_at": datetime.now(timezone.utc).isoformat(),
                    "title": title,
                    "text": text,
                    "date": None,
                    "url": pdf_url,
                    "instrument_type": instrument_type,
                }

                yield record
                count += 1
                logger.info(f"  [{count}] {title[:50]} ({len(text)} chars)")

        logger.info(f"Completed: {count} total records")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """SAARC documents are rarely updated; full refresh is preferred."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Records are already normalized during fetch."""
        return raw


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/SAARC-Legal bootstrap")
    subparsers = parser.add_subparsers(dest="command")

    boot_parser = subparsers.add_parser("bootstrap")
    boot_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot_parser.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast")

    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample = getattr(args, "sample", False) and args.command != "bootstrap-fast"
        full = getattr(args, "full", False) or args.command == "bootstrap-fast"

        scraper = SAARCLegalScraper()
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        records = []
        for record in scraper.fetch_all(sample=not full):
            records.append(record)
            # Save each record
            fname = re.sub(r"[^a-z0-9_-]", "_", record["_id"][:60]) + ".json"
            out_path = sample_dir / fname
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(records)} records to {sample_dir}")

        # Summary
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
