#!/usr/bin/env python3
"""
RW/OfficialGazette -- Rwanda Legislation via RwandaLII (Laws.Africa)

Fetches ~500 Rwandan laws with full text from rwandalii.org.
Laws are in Akoma Ntoso (AKN) markup; we extract clean text from the HTML.

Strategy:
  - Paginated listing at /legislation/?page=N (50 per page, ~10 pages)
  - Each law page has full AKN HTML; extract text from akn-body div

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
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.RW.OfficialGazette")

BASE_URL = "https://rwandalii.org"
LIST_URL = f"{BASE_URL}/legislation/"
MAX_PAGES = 15  # ~10 pages expected, extra margin


def strip_html(html_fragment: str) -> str:
    """Strip HTML tags and clean whitespace."""
    text = re.sub(r"<br\s*/?>", "\n", html_fragment)
    text = re.sub(r"</(p|div|li|tr|h[1-6]|article|section)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class RwandaLIIScraper(BaseScraper):
    """Scraper for RW/OfficialGazette -- Rwanda Legislation via RwandaLII."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
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
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _fetch_law_urls(self, page: int) -> List[str]:
        """Fetch law detail URLs from a listing page."""
        url = f"{LIST_URL}?page={page}"
        resp = self._request(url)
        if resp is None:
            return []
        # Extract /akn/rw/... links
        links = re.findall(r'href="(/akn/rw/[^"]+)"', resp.text)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique.append(link)
        return unique

    def _extract_law_content(self, html: str) -> Dict[str, str]:
        """Extract title, text, date, and metadata from a law page."""
        result = {"text": "", "title": "", "date": "", "nature": ""}

        # Extract title from h1
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        if m:
            result["title"] = strip_html(m.group(1))

        # Extract date from meta or page content
        # Laws.Africa pages often have date in the URL or in metadata
        m = re.search(r'<time[^>]*datetime="([^"]+)"', html)
        if m:
            result["date"] = m.group(1)[:10]

        if not result["date"]:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
            if m:
                result["date"] = m.group(1)[:10]

        # Extract nature (Act, Regulation, etc.)
        m = re.search(r'"nature"\s*:\s*"([^"]+)"', html)
        if m:
            result["nature"] = m.group(1)

        # Extract full text from akn-body
        body_match = re.search(
            r'class="akn-body"[^>]*>(.*?)(?=<(?:footer|div\s+class="(?!akn-))|$)',
            html,
            re.DOTALL,
        )
        if body_match:
            result["text"] = strip_html(body_match.group(1))
        else:
            # Fallback: try akn-akomaNtoso container
            akn_match = re.search(
                r'class="akn-akomaNtoso"[^>]*>(.*?)</article>',
                html,
                re.DOTALL,
            )
            if akn_match:
                result["text"] = strip_html(akn_match.group(1))

        return result

    def _parse_date_from_url(self, url_path: str) -> str:
        """Try to extract a date from the AKN URL path."""
        # Pattern: /akn/rw/act/law/YYYY/NN/eng@YYYY-MM-DD
        m = re.search(r"eng@(\d{4}-\d{2}-\d{2})", url_path)
        if m:
            return m.group(1)
        # Fallback: extract year from path
        m = re.search(r"/(\d{4})/", url_path)
        if m:
            return f"{m.group(1)}-01-01"
        return ""

    def _classify_law_type(self, url_path: str) -> str:
        """Classify the law type from the AKN URL."""
        parts = url_path.strip("/").split("/")
        # /akn/rw/act/{type}/{year}/{number}/...
        if len(parts) >= 5:
            return parts[3]  # law, mo, reg, decree, etc.
        return "unknown"

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("frbr_uri", ""),
            "_source": "RW/OfficialGazette",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "law_type": raw.get("law_type", ""),
            "nature": raw.get("nature", ""),
            "url": raw.get("url", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        seen_uris = set()

        for page_num in range(1, MAX_PAGES + 1):
            law_paths = self._fetch_law_urls(page_num)
            if not law_paths:
                logger.info(f"No laws on page {page_num}, stopping pagination")
                break

            logger.info(f"Page {page_num}: {len(law_paths)} laws listed")

            for path in law_paths:
                if max_records and count >= max_records:
                    return

                # Extract FRBR URI (path without the point-in-time suffix)
                frbr_uri = re.sub(r"/eng@.*$", "", path)
                if frbr_uri in seen_uris:
                    continue
                seen_uris.add(frbr_uri)

                detail_url = f"{BASE_URL}{path}"
                resp = self._request(detail_url)
                if resp is None:
                    logger.warning(f"Failed to fetch: {path}")
                    continue

                extracted = self._extract_law_content(resp.text)
                if not extracted["text"] or len(extracted["text"]) < 50:
                    logger.warning(
                        f"Insufficient text ({len(extracted.get('text', ''))} chars): {path}"
                    )
                    continue

                date = extracted["date"] or self._parse_date_from_url(path)

                raw = {
                    "frbr_uri": frbr_uri,
                    "title": extracted["title"],
                    "text": extracted["text"],
                    "date": date,
                    "law_type": self._classify_law_type(path),
                    "nature": extracted["nature"],
                    "url": detail_url,
                }
                count += 1
                yield raw

        logger.info(f"Completed: {count} laws fetched")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(max_records=20)

    def test(self) -> bool:
        law_paths = self._fetch_law_urls(1)
        if not law_paths:
            logger.error("Cannot fetch legislation listing from RwandaLII")
            return False

        logger.info(f"Listing OK: {len(law_paths)} laws on page 1")

        path = law_paths[0]
        resp = self._request(f"{BASE_URL}{path}")
        if resp:
            extracted = self._extract_law_content(resp.text)
            logger.info(
                f"Law OK: {path} "
                f"({len(extracted['text'])} chars, title={extracted['title'][:60]})"
            )
        else:
            logger.warning("Could not fetch sample law")

        return True


def main():
    parser = argparse.ArgumentParser(description="RW/OfficialGazette data fetcher (RwandaLII)")
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = RwandaLIIScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else None

        for record in scraper.fetch_all(max_records=max_records):
            normalized = scraper.normalize(record)
            out_path = sample_dir / f"record_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            logger.info(
                f"[{count+1}] {normalized['title'][:60]} "
                f"({len(normalized['text'])} chars)"
            )
            count += 1

        logger.info(f"Saved {count} records to {sample_dir}")

    elif args.command == "update":
        for record in scraper.fetch_updates():
            normalized = scraper.normalize(record)
            logger.info(f"Update: {normalized['title'][:60]}")


if __name__ == "__main__":
    main()
