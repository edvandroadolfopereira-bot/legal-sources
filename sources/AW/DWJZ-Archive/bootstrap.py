#!/usr/bin/env python3
"""
AW/DWJZ-Archive -- Aruba DWJZ Legislation on Internet Archive

Fetches ~5,600 Aruba legal documents from the Internet Archive collection
uploaded by DWJZ (Directie Wetgeving en Juridische Zaken). Includes
Afkondigingsbladen (official gazette), Landscouranten (national gazette),
consolidated law texts, and regulations.

Strategy:
  - Search API to enumerate all items by creator "DWJZ"
  - For each item, fetch pre-extracted DjVu text (_djvu.txt)
  - Falls back to PDF text extraction if no DjVu text available

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py bootstrap-fast --sample
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
from typing import Any, Dict, Generator, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AW.DWJZ-Archive")

SEARCH_URL = "https://archive.org/advancedsearch.php"
CREATOR = "DWJZ - Directie Wetgeving en Juridische Zaken"

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


class DWJZArchiveScraper(BaseScraper):
    """Scraper for AW/DWJZ-Archive — Aruba legislation on Internet Archive."""

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
                time.sleep(1.0)
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

    def _search_items(self, page: int = 1, rows: int = 100) -> dict:
        """Search Internet Archive for DWJZ items."""
        params = {
            "q": f'creator:"{CREATOR}"',
            "fl[]": ["identifier", "title", "date", "description"],
            "rows": rows,
            "page": page,
            "output": "json",
            "sort[]": "identifier asc",
        }
        resp = self._request(SEARCH_URL + "?" + "&".join(
            f"{k}={requests.utils.quote(str(v))}" if k != "fl[]" else f"fl[]={v}"
            for k, vs in params.items()
            for v in (vs if isinstance(vs, list) else [vs])
        ))
        if resp is None:
            return {"response": {"numFound": 0, "docs": []}}
        return resp.json()

    def _get_text_url(self, identifier: str) -> Optional[str]:
        """Get the DjVu text file URL for an item."""
        meta_url = f"https://archive.org/metadata/{identifier}/files"
        resp = self._request(meta_url)
        if resp is None:
            return None
        try:
            files = resp.json().get("result", [])
        except Exception:
            return None

        # Prefer DjVu text, then OCR text
        for f in files:
            name = f.get("name", "")
            if name.endswith("_djvu.txt"):
                return f"https://archive.org/download/{identifier}/{name}"

        # Fallback: look for PDF
        for f in files:
            name = f.get("name", "")
            fmt = f.get("format", "")
            if name.endswith(".pdf") and "Text PDF" in fmt:
                return f"https://archive.org/download/{identifier}/{name}"
            if name.endswith(".pdf") and "PDF" in fmt:
                return f"https://archive.org/download/{identifier}/{name}"

        return None

    def _fetch_text(self, url: str) -> str:
        """Fetch text content from URL (text file or PDF)."""
        resp = self._request(url, timeout=120)
        if resp is None:
            return ""

        if url.endswith(".txt") or url.endswith(".txt.gz"):
            return resp.text.strip()

        # PDF fallback
        if url.endswith(".pdf") and PdfReader is not None:
            try:
                reader = PdfReader(io.BytesIO(resp.content))
                pages = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
                text = "\n\n".join(pages).strip()
                text = re.sub(r"\n{3,}", "\n\n", text)
                return text
            except Exception as e:
                logger.warning(f"PDF extraction error: {e}")
                return ""

        return resp.text.strip()

    def _extract_date(self, date_str: str) -> str:
        """Extract ISO date from IA date string."""
        if not date_str:
            return ""
        # IA dates can be "2021-01-21T00:00:00Z" or "2021"
        m = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
        if m:
            return m.group(1)
        m = re.match(r"(\d{4})", date_str)
        if m:
            return f"{m.group(1)}-01-01"
        return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "AW/DWJZ-Archive",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "identifier": raw.get("identifier", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        skipped = 0
        page = 1
        rows = 100

        while True:
            if max_records and count >= max_records:
                break

            data = self._search_items(page=page, rows=rows)
            docs = data.get("response", {}).get("docs", [])
            if not docs:
                break

            for doc in docs:
                if max_records and count >= max_records:
                    break

                identifier = doc.get("identifier", "")
                title = doc.get("title", "")
                date_str = doc.get("date", "")
                if isinstance(date_str, list):
                    date_str = date_str[0] if date_str else ""

                text_url = self._get_text_url(identifier)
                if not text_url:
                    logger.warning(f"No text file for: {identifier}")
                    skipped += 1
                    continue

                text = self._fetch_text(text_url)
                if not text or len(text) < 50:
                    logger.warning(f"Insufficient text ({len(text)} chars): {identifier}")
                    skipped += 1
                    continue

                date = self._extract_date(date_str)

                raw = {
                    "doc_id": f"AW-DWJZ-{identifier}",
                    "title": title if title else identifier,
                    "text": text,
                    "date": date,
                    "url": f"https://archive.org/details/{identifier}",
                    "identifier": identifier,
                }
                count += 1
                yield raw

            if len(docs) < rows:
                break
            page += 1

        logger.info(f"Completed: {count} documents fetched, {skipped} skipped")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(max_records=20)

    def test(self) -> bool:
        data = self._search_items(page=1, rows=1)
        total = data.get("response", {}).get("numFound", 0)
        if total == 0:
            logger.error("No items found in DWJZ collection")
            return False

        logger.info(f"API OK: {total} total items in DWJZ collection")

        docs = data["response"]["docs"]
        if docs:
            identifier = docs[0]["identifier"]
            text_url = self._get_text_url(identifier)
            if text_url:
                text = self._fetch_text(text_url)
                logger.info(f"Text OK: {identifier} ({len(text)} chars)")
            else:
                logger.warning(f"No text file found for: {identifier}")
        return True


def main():
    parser = argparse.ArgumentParser(description="AW/DWJZ-Archive data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = DWJZArchiveScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else None

        for record in scraper.fetch_all(max_records=max_records):
            normalized = scraper.normalize(record)
            out_path = sample_dir / f"record_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            text_len = len(normalized.get("text", ""))
            logger.info(
                f"[{count + 1}] {normalized.get('title', '?')[:80]} "
                f"({text_len:,} chars)"
            )
            count += 1

        logger.info(f"Bootstrap complete: {count} records saved to sample/")

    elif args.command == "update":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for record in scraper.fetch_updates():
            normalized = scraper.normalize(record)
            out_path = sample_dir / f"update_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            count += 1
        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
