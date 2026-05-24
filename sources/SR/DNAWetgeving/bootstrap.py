#!/usr/bin/env python3
"""
SR/DNAWetgeving -- Suriname Parliament Legislation (DNA)

Fetches ~320 Suriname laws from dna.sr (De Nationale Assemblee).
Pre-2005 consolidated texts (~186) have text-extractable PDFs.
Post-2005 laws (~137) are mostly scanned PDFs; text extraction attempted.

Strategy:
  - Scrape index pages for law links (geldende-teksten-t-m-2005, wetten-na-2005)
  - Fetch each law page for PDF URL
  - Download PDF and extract text via pypdf

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py test
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SR.DNAWetgeving")

BASE_URL = "https://www.dna.sr"

INDEX_PAGES = [
    (
        f"{BASE_URL}/wetgeving/surinaamse-wetten/geldende-teksten-t-m-2005/",
        "geldende-teksten-t-m-2005",
    ),
    (
        f"{BASE_URL}/wetgeving/surinaamse-wetten/wetten-na-2005/",
        "wetten-na-2005",
    ),
]

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
    logger.warning("pypdf not installed; PDF text extraction unavailable")


class DNAWetgevingScraper(BaseScraper):
    """Scraper for SR/DNAWetgeving -- Suriname Parliament Laws."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.5",
        })

    def _request(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(1.5)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 30s")
                    time.sleep(30)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _get_law_links(self, index_url: str, section: str) -> List[Tuple[str, str, str]]:
        """Scrape index page for (title, law_page_url, section) tuples."""
        from html.parser import HTMLParser

        resp = self._request(index_url)
        if resp is None:
            return []

        class LinkExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
                self.current_href = None
                self.current_text = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    attrs_d = dict(attrs)
                    href = attrs_d.get("href", "")
                    if f"/{section}/" in href and href != f"/wetgeving/surinaamse-wetten/{section}/" and href.count("/") > 4:
                        self.current_href = href
                        self.current_text = []

            def handle_data(self, data):
                if self.current_href is not None:
                    self.current_text.append(data)

            def handle_endtag(self, tag):
                if tag == "a" and self.current_href is not None:
                    title = "".join(self.current_text).strip()
                    if title:
                        full_url = BASE_URL + self.current_href if self.current_href.startswith("/") else self.current_href
                        self.links.append((title, full_url, section))
                    self.current_href = None

        parser = LinkExtractor()
        parser.feed(resp.text)
        return parser.links

    def _get_pdf_url(self, law_page_url: str) -> Optional[str]:
        """Fetch a law page and extract the PDF download URL."""
        resp = self._request(law_page_url)
        if resp is None:
            return None

        # Look for PDF link in HTML
        m = re.search(r'href="([^"]*\.pdf[^"]*)"', resp.text, re.IGNORECASE)
        if m:
            pdf_path = m.group(1)
            if pdf_path.startswith("/"):
                return BASE_URL + pdf_path
            return pdf_path
        return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pypdf."""
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text).strip()
            # Clean up common artifacts
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            return full_text
        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
            return ""

    def _extract_year(self, title: str) -> Optional[str]:
        """Try to extract a year from the law title."""
        m = re.search(r"(\d{4})", title)
        if m:
            year = int(m.group(1))
            if 1800 <= year <= 2030:
                return m.group(1)
        return None

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("law_id", ""),
            "_source": "SR/DNAWetgeving",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "pdf_url": raw.get("pdf_url", ""),
            "section": raw.get("section", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        seen_ids = set()

        for index_url, section in INDEX_PAGES:
            law_links = self._get_law_links(index_url, section)
            logger.info(f"Section '{section}': {len(law_links)} laws found")

            for title, law_url, sec in law_links:
                if max_records and count >= max_records:
                    return

                # Create a stable ID from the URL slug
                slug = law_url.rstrip("/").split("/")[-1]
                law_id = f"SR-DNA-{slug}"

                if law_id in seen_ids:
                    continue
                seen_ids.add(law_id)

                pdf_url = self._get_pdf_url(law_url)
                if not pdf_url:
                    logger.warning(f"No PDF found for: {title}")
                    continue

                # Download PDF
                resp = self._request(pdf_url, timeout=120)
                if resp is None:
                    logger.warning(f"Failed to download PDF: {pdf_url}")
                    continue

                # Skip very large PDFs (>50MB)
                if len(resp.content) > 50 * 1024 * 1024:
                    logger.warning(f"PDF too large ({len(resp.content)} bytes): {title}")
                    continue

                text = self._extract_pdf_text(resp.content)
                if not text or len(text) < 100:
                    logger.warning(
                        f"Insufficient text ({len(text)} chars) from PDF: {title}"
                    )
                    continue

                year = self._extract_year(title)
                date = f"{year}-01-01" if year else ""

                raw = {
                    "law_id": law_id,
                    "title": title,
                    "text": text,
                    "date": date,
                    "url": law_url,
                    "pdf_url": pdf_url,
                    "section": sec,
                }
                count += 1
                yield raw

        logger.info(f"Completed: {count} laws fetched with full text")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(max_records=20)

    def test(self) -> bool:
        law_links = self._get_law_links(INDEX_PAGES[0][0], INDEX_PAGES[0][1])
        if not law_links:
            logger.error("Cannot fetch law index from dna.sr")
            return False

        logger.info(f"Index OK: {len(law_links)} laws on first page")

        if law_links:
            title, url, sec = law_links[0]
            pdf_url = self._get_pdf_url(url)
            if pdf_url:
                resp = self._request(pdf_url, timeout=120)
                if resp:
                    text = self._extract_pdf_text(resp.content)
                    logger.info(f"PDF OK: {title} ({len(text)} chars)")
                else:
                    logger.warning("Could not download sample PDF")
            else:
                logger.warning("No PDF URL found on sample page")

        return True


def main():
    parser = argparse.ArgumentParser(description="SR/DNAWetgeving data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = DNAWetgevingScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else None

        for record in scraper.fetch_all(max_records=max_records):
            out_path = sample_dir / f"record_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            text_len = len(record.get("text", ""))
            logger.info(
                f"[{count + 1}] {record.get('title', '?')[:80]} "
                f"({text_len:,} chars)"
            )
            count += 1

        logger.info(f"Bootstrap complete: {count} records saved to sample/")

    elif args.command == "update":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for record in scraper.fetch_updates():
            out_path = sample_dir / f"update_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
