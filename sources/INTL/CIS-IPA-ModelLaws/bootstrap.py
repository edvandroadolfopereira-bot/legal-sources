#!/usr/bin/env python3
"""
INTL/CIS-IPA-ModelLaws -- CIS Interparliamentary Assembly Model Laws

Fetches model codes, laws, and recommendations from the CIS IPA website.

Strategy:
  - Paginate through the model laws listing at iacis.ru
  - Parse HTML for document titles, dates, and DOCX download links
  - Download DOCX files and extract text using python-docx
  - Normalize into standard LDH schema

Data:
  - ~500 model legislative acts
  - Russian language
  - DOCX format
  - No authentication required

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch all (same as bootstrap)
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List, Tuple

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup4 required. pip install beautifulsoup4")
    sys.exit(1)

try:
    import docx
except ImportError:
    print("ERROR: python-docx required. pip install python-docx")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.CIS-IPA-ModelLaws")

BASE_URL = "https://iacis.ru"
LISTING_PATH = "/baza_dokumentov/modelnie_zakonodatelnie_akti_i_rekomendatcii_mpa_sng/modelnie_kodeksi_i_zakoni"
PAGE_SIZE = 10


class CISIPAScraper(BaseScraper):
    """Scraper for INTL/CIS-IPA-ModelLaws."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        })

    def _extract_docx_text(self, content: bytes) -> Optional[str]:
        """Extract text from a DOCX file."""
        try:
            doc = docx.Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)
            return text if len(text) > 20 else None
        except Exception as e:
            logger.warning("DOCX extraction failed: %s", e)
            return None

    def _parse_listing_page(self, html: str) -> List[Dict[str, str]]:
        """Parse a listing page and extract document entries."""
        soup = BeautifulSoup(html, "html.parser")
        entries = []

        for item in soup.select("div.document-item, div.doc-item, tr, li"):
            link = item.find("a", href=re.compile(r"/mod_file/p_file/\d+"))
            if not link:
                continue

            title_el = item.find("a", href=True)
            title = title_el.get_text(strip=True) if title_el else ""

            # Look for date in nearby text
            text = item.get_text()
            date_match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
            date_str = ""
            if date_match:
                date_str = date_match.group(0)

            download_url = link.get("href", "")
            if download_url and not download_url.startswith("http"):
                download_url = BASE_URL + download_url

            if title and download_url:
                entries.append({
                    "title": title,
                    "date_raw": date_str,
                    "download_url": download_url,
                })

        # Fallback: try broader parsing if structured elements not found
        if not entries:
            for link in soup.find_all("a", href=re.compile(r"/mod_file/p_file/\d+")):
                title = link.get_text(strip=True)
                download_url = link.get("href", "")
                if download_url and not download_url.startswith("http"):
                    download_url = BASE_URL + download_url
                if title and download_url:
                    # Find nearby date
                    parent = link.find_parent()
                    date_str = ""
                    if parent:
                        txt = parent.get_text()
                        dm = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", txt)
                        if dm:
                            date_str = dm.group(0)
                    entries.append({
                        "title": title,
                        "date_raw": date_str,
                        "download_url": download_url,
                    })

        return entries

    def _parse_russian_date(self, date_str: str) -> Optional[str]:
        """Parse Russian date string to ISO format."""
        months = {
            "января": "01", "февраля": "02", "марта": "03",
            "апреля": "04", "мая": "05", "июня": "06",
            "июля": "07", "августа": "08", "сентября": "09",
            "октября": "10", "ноября": "11", "декабря": "12",
        }
        match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
        if match:
            day, month_name, year = match.groups()
            month = months.get(month_name.lower())
            if month:
                return f"{year}-{month}-{int(day):02d}"
        return None

    def _fetch_entries(self, limit: Optional[int] = None) -> Generator[Dict, None, None]:
        """Paginate through all listing pages."""
        offset = 0
        total = 0
        while True:
            url = BASE_URL + LISTING_PATH
            if offset > 0:
                url += f"/{offset}"

            self.rate_limiter.wait()
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.error("Failed to fetch page at offset %d: %s", offset, e)
                break

            entries = self._parse_listing_page(resp.text)
            if not entries:
                break

            for entry in entries:
                yield entry
                total += 1
                if limit and total >= limit:
                    return

            offset += PAGE_SIZE
            if len(entries) < PAGE_SIZE:
                break

    def _download_and_normalize(self, entry: Dict) -> Optional[Dict[str, Any]]:
        """Download DOCX and normalize to LDH schema."""
        title = entry["title"]
        download_url = entry["download_url"]

        self.rate_limiter.wait()
        try:
            resp = self.session.get(download_url, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to download %s: %s", title[:50], e)
            return None

        text = self._extract_docx_text(resp.content)
        if not text:
            logger.warning("No text extracted from: %s", title[:50])
            return None

        date_iso = self._parse_russian_date(entry.get("date_raw", ""))

        # Extract file ID from URL
        file_id_match = re.search(r"/p_file/(\d+)", download_url)
        file_id = file_id_match.group(1) if file_id_match else str(hash(title))

        return {
            "_id": f"cis-ipa-{file_id}",
            "_source": "INTL/CIS-IPA-ModelLaws",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": download_url,
            "language": "ru",
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        count = 0
        for entry in self._fetch_entries():
            record = self._download_and_normalize(entry)
            if record:
                count += 1
                yield record
                if count % 20 == 0:
                    logger.info("Processed %d records", count)
        logger.info("Total: %d records", count)

    def fetch_sample(self, n: int = 15) -> Generator[Dict[str, Any], None, None]:
        count = 0
        for entry in self._fetch_entries(limit=n * 2):
            record = self._download_and_normalize(entry)
            if record:
                count += 1
                yield record
                if count >= n:
                    return

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/CIS-IPA-ModelLaws scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = CISIPAScraper()
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command == "test":
        logger.info("Testing connectivity...")
        try:
            resp = scraper.session.get(BASE_URL + LISTING_PATH, timeout=15)
            resp.raise_for_status()
            entries = scraper._parse_listing_page(resp.text)
            logger.info("Connected. Found %d entries on first page.", len(entries))
        except Exception as e:
            logger.error("Connection failed: %s", e)
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample or not args.full:
            logger.info("Fetching sample records...")
            count = 0
            for record in scraper.fetch_sample(15):
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                text_len = len(record.get("text", ""))
                logger.info("[%d] %s (%d chars)", count, record["title"][:60], text_len)
                count += 1
            logger.info("Saved %d sample records to %s", count, sample_dir)
        else:
            logger.info("Fetching all records...")
            count = 0
            for record in scraper.fetch_all():
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                count += 1
            logger.info("Saved %d records", count)
    elif args.command == "update":
        count = 0
        for record in scraper.fetch_all():
            count += 1
        logger.info("Fetched %d records", count)


if __name__ == "__main__":
    main()
