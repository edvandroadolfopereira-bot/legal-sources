#!/usr/bin/env python3
"""
BT/BICMA-Regulations -- Bhutan InfoComm and Media Authority — ICT & Media Regulations

Fetches ICT, telecom, media, and content regulations from BICMA's Rules & Regulations page.
All documents are English-language PDFs with extractable text.

Strategy:
  - Scrape the Rules and Regulations page (page_id=242) for PDF links
  - Also check the ICM Act page (page_id=31)
  - Download each PDF and extract full text via common.pdf_extract

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py test
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BT.BICMA-Regulations")

BASE_URL = "https://www.bicma.gov.bt"

# Pages containing PDF links to regulations
REGULATION_PAGES = [
    "https://www.bicma.gov.bt/?page_id=242",  # Rules and Regulations
    "https://www.bicma.gov.bt/?page_id=31",    # ICM Act of Bhutan
]


class _PDFLinkExtractor(HTMLParser):
    """Extract PDF links and their anchor text from HTML."""

    def __init__(self):
        super().__init__()
        self.in_pdf_link = False
        self.current_url = ""
        self.current_text_parts: List[str] = []
        self.links: List[Tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = d.get("href", "")
            if href.lower().endswith(".pdf") or href.lower().endswith('.pdf"'):
                self.in_pdf_link = True
                self.current_url = href.rstrip('"')
                self.current_text_parts = []

    def handle_data(self, data):
        if self.in_pdf_link:
            self.current_text_parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self.in_pdf_link:
            title = " ".join(self.current_text_parts).strip()
            if self.current_url:
                self.links.append((title, self.current_url))
            self.in_pdf_link = False


def _clean_title(title: str, url: str) -> str:
    """Clean up a document title, falling back to URL-derived title."""
    title = unescape(title).strip()
    if not title or len(title) < 3:
        fname = unquote(url.rsplit("/", 1)[-1])
        fname = fname.replace(".pdf", "").replace("-", " ").replace("_", " ")
        fname = re.sub(r"\s+", " ", fname).strip()
        title = fname
    return title


def _make_id(url: str) -> str:
    """Create a stable document ID from the PDF URL."""
    fname = unquote(url.rsplit("/", 1)[-1])
    fname = fname.replace(".pdf", "").strip()
    fname = re.sub(r"[^a-zA-Z0-9_-]", "_", fname)
    fname = re.sub(r"_+", "_", fname).strip("_")
    return fname[:120]


def _is_regulation_pdf(url: str) -> bool:
    """Filter out non-regulation PDFs (forms, leave requests, brochures)."""
    skip_patterns = [
        "Leave-Form",
        "leave-form",
        "Annual-Leave",
        "annual-leave",
        "Application_Form",
        "application_form",
        "brochure/",
        "complaint_redressal/",
        "license_permit_forms/",
    ]
    url_lower = url.lower()
    return not any(pat.lower() in url_lower for pat in skip_patterns)


class BICMARegulationsScraper(BaseScraper):
    """Scraper for BT/BICMA-Regulations -- Bhutan ICT & media regulations PDFs."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
        })

    def _request(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(2)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 30s")
                    time.sleep(30)
                    continue
                if resp.status_code == 404:
                    logger.warning(f"404 for {url}")
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _get_pdf_list(self) -> List[Tuple[str, str]]:
        """Scrape regulation pages for PDF links and titles."""
        seen_urls = set()
        results = []

        for page_url in REGULATION_PAGES:
            resp = self._request(page_url)
            if resp is None:
                logger.warning(f"Cannot fetch {page_url}")
                continue

            parser = _PDFLinkExtractor()
            parser.feed(resp.text)

            for title, url in parser.links:
                full_url = urljoin(page_url, unescape(url))
                norm_url = unquote(full_url).lower()
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)

                if not _is_regulation_pdf(full_url):
                    continue

                title = _clean_title(title, full_url)
                results.append((title, full_url))

        logger.info(f"Found {len(results)} regulation PDFs across all pages")
        return results

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "BT/BICMA-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", None),
            "url": raw.get("url", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        pdf_list = self._get_pdf_list()
        if not pdf_list:
            logger.error("No PDFs found")
            return

        count = 0
        for title, url in pdf_list:
            if max_records and count >= max_records:
                return

            doc_id = _make_id(url)
            logger.info(f"Downloading: {title}")

            text = extract_pdf_markdown(
                source="BT/BICMA-Regulations",
                source_id=doc_id,
                pdf_url=url,
                table="legislation",
            )

            if not text or len(text) < 100:
                logger.warning(f"Insufficient text ({len(text or '')} chars): {title}")
                continue

            date = None
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", title)
            if year_match:
                date = f"{year_match.group(1)}-01-01"

            raw = {
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "date": date,
                "url": url,
            }
            count += 1
            yield raw

        logger.info(f"Completed: {count} documents fetched")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def test(self) -> bool:
        pdf_list = self._get_pdf_list()
        if not pdf_list:
            logger.error("Cannot fetch PDF list")
            return False

        logger.info(f"Regulation pages OK: {len(pdf_list)} PDFs found")

        title, url = pdf_list[0]
        logger.info(f"Testing download: {title}")
        text = extract_pdf_markdown(
            source="BT/BICMA-Regulations",
            source_id="test",
            pdf_url=url,
            table="legislation",
            force=True,
        )
        if text:
            logger.info(f"PDF extraction OK: {len(text)} chars")
        else:
            logger.warning("PDF extraction returned no text")

        return True


def main():
    parser = argparse.ArgumentParser(description="BT/BICMA-Regulations data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = BICMARegulationsScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.bootstrap(sample_mode=args.sample, sample_size=15)
    elif args.command == "update":
        scraper.bootstrap(sample_mode=False)


if __name__ == "__main__":
    main()
