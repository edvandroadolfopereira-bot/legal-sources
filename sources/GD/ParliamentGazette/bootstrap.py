#!/usr/bin/env python3
"""
GD/ParliamentGazette -- Grenada Government Gazette (Parliament)

Fetches ~157 Grenada Government Gazette documents (acts, SROs, gazette issues)
with full text from grenadaparliament.gd. PDFs are downloaded and text extracted
via pdfplumber.

Strategy:
  - RSS feed pagination to discover all documents
  - Visit each document page to find PDF link
  - Download PDF and extract text with pdfplumber

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
from html import unescape
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from xml.etree import ElementTree as ET

import pdfplumber
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GD.ParliamentGazette")

BASE_URL = "https://grenadaparliament.gd"
FEED_URL = f"{BASE_URL}/cat_doc/the-grenadian-government-gazette/feed/"
MAX_FEED_PAGES = 25
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB limit per PDF


class GDParliamentGazetteScraper(BaseScraper):
    """Scraper for GD/ParliamentGazette -- Grenada Government Gazette."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _request(self, url: str, timeout: int = 60, stream: bool = False) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(2)
                resp = self.session.get(url, timeout=timeout, stream=stream)
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

    def _parse_rss_page(self, page: int) -> List[Dict[str, str]]:
        """Parse one page of the RSS feed, returning list of {title, link, pubDate, guid}."""
        url = f"{FEED_URL}?paged={page}"
        resp = self._request(url)
        if resp is None or not resp.text.strip():
            return []

        items = []
        try:
            root = ET.fromstring(resp.text)
            ns = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "content": "http://purl.org/rss/1.0/modules/content/",
            }
            for item_el in root.findall(".//item"):
                title_el = item_el.find("title")
                link_el = item_el.find("link")
                pub_el = item_el.find("pubDate")
                guid_el = item_el.find("guid")

                title = unescape(title_el.text.strip()) if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
                guid = guid_el.text.strip() if guid_el is not None and guid_el.text else ""

                if link:
                    items.append({
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "guid": guid,
                    })
        except ET.ParseError as e:
            logger.warning(f"XML parse error on feed page {page}: {e}")

        return items

    def _find_pdf_url(self, doc_page_url: str) -> Optional[str]:
        """Visit a document page and find the PDF download link."""
        resp = self._request(doc_page_url)
        if resp is None:
            return None

        pdf_links = re.findall(r'href="([^"]*\.pdf)"', resp.text)
        # Filter for wp-content/uploads PDFs (the actual documents)
        upload_pdfs = [u for u in pdf_links if "wp-content/uploads" in u]
        if upload_pdfs:
            return upload_pdfs[0]
        if pdf_links:
            return pdf_links[0]
        return None

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download PDF and extract text via pdfplumber."""
        resp = self._request(pdf_url, timeout=120, stream=True)
        if resp is None:
            return ""

        # Check content length
        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({int(cl)} bytes): {pdf_url}")
            return ""

        pdf_bytes = resp.content
        if len(pdf_bytes) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({len(pdf_bytes)} bytes): {pdf_url}")
            return ""

        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            pdf.close()
            return "\n\n".join(parts).strip()
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return ""

    def _parse_pub_date(self, pub_date_str: str) -> str:
        """Convert RSS pubDate to ISO 8601 date."""
        if not pub_date_str:
            return ""
        try:
            # Format: "Fri, 24 Apr 2026 19:30:57 +0000"
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub_date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return ""

    def _generate_id(self, doc: Dict[str, str]) -> str:
        """Generate a stable ID from the document URL slug."""
        slug = doc["link"].rstrip("/").split("/")[-1]
        return f"GD-gazette-{slug}"

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "GD/ParliamentGazette",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "pdf_url": raw.get("pdf_url", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        seen_links = set()

        for page_num in range(1, MAX_FEED_PAGES + 1):
            items = self._parse_rss_page(page_num)
            if not items:
                logger.info(f"No items on feed page {page_num}, stopping")
                break

            logger.info(f"Feed page {page_num}: {len(items)} items")

            for doc in items:
                if max_records and count >= max_records:
                    return

                link = doc["link"]
                if link in seen_links:
                    continue
                seen_links.add(link)

                # Find PDF URL
                pdf_url = self._find_pdf_url(link)
                if not pdf_url:
                    logger.warning(f"No PDF found for: {doc['title']}")
                    continue

                # Extract text from PDF
                text = self._extract_pdf_text(pdf_url)
                if not text or len(text) < 100:
                    logger.warning(
                        f"Insufficient text ({len(text)} chars) from PDF: {doc['title']}"
                    )
                    continue

                date = self._parse_pub_date(doc["pub_date"])
                doc_id = self._generate_id(doc)

                raw = {
                    "doc_id": doc_id,
                    "title": doc["title"],
                    "text": text,
                    "date": date,
                    "url": link,
                    "pdf_url": pdf_url,
                }
                count += 1
                yield raw

        logger.info(f"Completed: {count} documents fetched")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(max_records=20)

    def test(self) -> bool:
        items = self._parse_rss_page(1)
        if not items:
            logger.error("Cannot fetch RSS feed")
            return False

        logger.info(f"RSS feed OK: {len(items)} items on page 1")

        doc = items[0]
        pdf_url = self._find_pdf_url(doc["link"])
        if pdf_url:
            logger.info(f"PDF URL found: {pdf_url}")
            text = self._extract_pdf_text(pdf_url)
            logger.info(f"PDF text: {len(text)} chars")
        else:
            logger.warning("No PDF found for first document")

        return True


def main():
    parser = argparse.ArgumentParser(description="GD/ParliamentGazette data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = GDParliamentGazetteScraper()

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
