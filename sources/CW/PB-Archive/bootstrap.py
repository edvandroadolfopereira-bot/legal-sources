#!/usr/bin/env python3
"""
CW/PB-Archive -- Curaçao Publicatieblad on Internet Archive

Fetches ~5,700 historical Curaçao gazette issues from the Internet Archive,
digitized by the Royal Dutch National Library (KB). Covers the colonial-era
Publicatieblad van Curaçao en onderhoorigheden (1861-1954).

Strategy:
  - Search API to enumerate all items matching "Publicatieblad" + "Curaçao"
  - For each item, fetch pre-extracted DjVu text
  - Falls back to PDF text extraction if no DjVu text

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
from typing import Any, Dict, Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.CW.PB-Archive")

SEARCH_URL = "https://archive.org/advancedsearch.php"
QUERY = 'title:"Publicatieblad" AND title:"Curaçao"'

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


class PBArchiveScraper(BaseScraper):
    """Scraper for CW/PB-Archive — Curaçao historical gazette on Internet Archive."""

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

        for f in files:
            name = f.get("name", "")
            if name.endswith("_djvu.txt"):
                return f"https://archive.org/download/{identifier}/{name}"

        for f in files:
            name = f.get("name", "")
            fmt = f.get("format", "")
            if name.endswith(".pdf") and "PDF" in fmt:
                return f"https://archive.org/download/{identifier}/{name}"

        return None

    def _fetch_text(self, url: str) -> str:
        resp = self._request(url, timeout=120)
        if resp is None:
            return ""

        if url.endswith(".txt") or url.endswith(".txt.gz"):
            return resp.text.strip()

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
        if not date_str:
            return ""
        m = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
        if m:
            return m.group(1)
        m = re.match(r"(\d{4})", date_str)
        if m:
            return f"{m.group(1)}-01-01"
        return ""

    def _extract_pb_ref(self, title: str) -> str:
        """Extract P.B. reference from title (e.g. '1899 no. 24')."""
        m = re.search(r"(\d{4})\s*no\.\s*(\d+)", title, re.IGNORECASE)
        if m:
            return f"P.B. {m.group(1)} no. {m.group(2)}"
        return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "CW/PB-Archive",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "identifier": raw.get("identifier", ""),
            "pb_reference": raw.get("pb_reference", ""),
        }

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        skipped = 0
        page = 1
        rows = 100

        while True:
            if max_records and count >= max_records:
                break

            params = {
                "q": QUERY,
                "fl[]": ["identifier", "title", "date"],
                "rows": rows,
                "page": page,
                "output": "json",
                "sort[]": "identifier asc",
            }
            resp = self._request(
                SEARCH_URL + "?" + "&".join(
                    f"{k}={requests.utils.quote(str(v))}" if k != "fl[]" else f"fl[]={v}"
                    for k, vs in params.items()
                    for v in (vs if isinstance(vs, list) else [vs])
                )
            )
            if resp is None:
                break
            data = resp.json()
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
                pb_ref = self._extract_pb_ref(title)

                raw = {
                    "doc_id": f"CW-PB-{identifier}",
                    "title": title if title else identifier,
                    "text": text,
                    "date": date,
                    "url": f"https://archive.org/details/{identifier}",
                    "identifier": identifier,
                    "pb_reference": pb_ref,
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
        params = {
            "q": QUERY,
            "fl[]": ["identifier", "title"],
            "rows": 1,
            "output": "json",
        }
        resp = self._request(
            SEARCH_URL + "?" + "&".join(
                f"{k}={requests.utils.quote(str(v))}" if k != "fl[]" else f"fl[]={v}"
                for k, vs in params.items()
                for v in (vs if isinstance(vs, list) else [vs])
            )
        )
        if resp is None:
            logger.error("Cannot reach Internet Archive API")
            return False

        data = resp.json()
        total = data.get("response", {}).get("numFound", 0)
        if total == 0:
            logger.error("No items found")
            return False

        logger.info(f"API OK: {total} total items")
        docs = data["response"]["docs"]
        if docs:
            identifier = docs[0]["identifier"]
            text_url = self._get_text_url(identifier)
            if text_url:
                text = self._fetch_text(text_url)
                logger.info(f"Text OK: {identifier} ({len(text)} chars)")
        return True


def main():
    parser = argparse.ArgumentParser(description="CW/PB-Archive data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
    )
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = PBArchiveScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)

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
            logger.info(f"[{count + 1}] {normalized.get('title', '?')[:80]} ({text_len:,} chars)")
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
