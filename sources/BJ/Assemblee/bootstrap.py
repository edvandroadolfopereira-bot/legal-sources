#!/usr/bin/env python3
"""
BJ/Assemblee - Benin National Assembly Laws

Fetches laws from the National Assembly's documentation portal (documentation-anbenin.org).
Uses the Omeka S REST API for metadata and downloads PDFs for full text extraction.

Data source: https://documentation-anbenin.org
License: Public domain (official government laws)
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
from typing import Any, Dict, Iterator, List, Optional

import pdfplumber
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://documentation-anbenin.org"
API_URL = f"{BASE_URL}/api"
SOURCE_ID = "BJ/Assemblee"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"
PER_PAGE = 50
DELAY = 0.5


class AssembleeFetcher:
    """Fetcher for Benin National Assembly laws via Omeka S API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def get_items(self, page: int = 1, per_page: int = PER_PAGE) -> List[Dict]:
        """Fetch a page of items from the Omeka S API."""
        params = {"per_page": per_page, "page": page}
        try:
            resp = self.session.get(f"{API_URL}/items", params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch items page {page}: {e}")
            return []

    def get_media(self, media_id: int) -> Optional[Dict]:
        """Fetch media metadata from the Omeka S API."""
        try:
            resp = self.session.get(f"{API_URL}/media/{media_id}", timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch media {media_id}: {e}")
            return None

    def extract_pdf_text(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF bytes using pdfplumber."""
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                full_text = "\n\n".join(pages_text)
                return full_text if len(full_text) > 50 else None
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return None

    def download_and_extract(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract its text."""
        time.sleep(DELAY)
        try:
            resp = self.session.get(pdf_url, timeout=120)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {pdf_url}")
                return None
            if len(resp.content) > 100_000_000:
                logger.warning(f"PDF too large ({len(resp.content)} bytes), skipping")
                return None
            return self.extract_pdf_text(resp.content)
        except requests.RequestException as e:
            logger.warning(f"Download failed for {pdf_url}: {e}")
            return None

    def extract_field(self, item: Dict, field: str) -> Optional[str]:
        """Extract a Dublin Core or other field value from an Omeka item."""
        values = item.get(field, [])
        if isinstance(values, list) and values:
            return values[0].get("@value")
        return None

    def parse_date(self, raw_date: Optional[str]) -> Optional[str]:
        """Parse various date formats into ISO 8601."""
        if not raw_date:
            return None

        # Try common formats
        for fmt in ["%d/%m/%y", "%d/%m/%Y", "%d %B %Y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(raw_date.strip(), fmt)
                if dt.year > 2050:
                    dt = dt.replace(year=dt.year - 100)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try extracting date from title like "du 13 janvier 1999"
        months_fr = {
            "janvier": 1, "février": 2, "mars": 3, "avril": 4,
            "mai": 5, "juin": 6, "juillet": 7, "août": 8,
            "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
        }
        # Handle "1er" as day 1
        cleaned = re.sub(r"\b1er\b", "1", raw_date)
        m = re.search(r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})", cleaned, re.IGNORECASE)
        if m:
            day, month_name, year = m.groups()
            month = months_fr.get(month_name.lower())
            if month:
                return f"{year}-{month:02d}-{int(day):02d}"

        return raw_date

    def process_item(self, item: Dict) -> Optional[Dict[str, Any]]:
        """Process a single Omeka item into a normalized record."""
        item_id = item.get("o:id")
        title = self.extract_field(item, "dcterms:title") or item.get("o:title", "")
        alt_title = self.extract_field(item, "dcterms:alternative") or ""
        law_number = self.extract_field(item, "bibo:number") or ""
        raw_date = self.extract_field(item, "dcterms:date") or self.extract_field(item, "dcterms:issued")

        # Get PDF URL from media
        media_list = item.get("o:media", [])
        if not media_list:
            logger.warning(f"Item {item_id} has no media")
            return None

        media_id = media_list[0].get("o:id")
        media = self.get_media(media_id)
        if not media:
            return None

        if media.get("o:media_type") != "application/pdf":
            logger.warning(f"Item {item_id} media is not PDF: {media.get('o:media_type')}")
            return None

        pdf_url = media.get("o:original_url")
        if not pdf_url:
            return None

        text = self.download_and_extract(pdf_url)
        if not text:
            logger.warning(f"No text extracted for item {item_id}: {title}")
            return None

        # Parse date from metadata or title
        date = self.parse_date(raw_date)
        if not date:
            date = self.parse_date(alt_title or title)

        display_title = alt_title if alt_title else title

        return {
            "_id": f"BJ-AN-{item_id}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": display_title,
            "text": text,
            "date": date,
            "law_number": law_number,
            "official_title": title,
            "alternative_title": alt_title,
            "url": f"{BASE_URL}/s/textes-de-lois/item/{item_id}",
            "pdf_url": pdf_url,
            "language": "fr",
            "country": "BJ",
            "omeka_id": item_id,
        }

    def fetch_all(self) -> Iterator[Dict[str, Any]]:
        """Yield all laws with full text."""
        page = 1
        while True:
            items = self.get_items(page=page)
            if not items:
                break
            for item in items:
                record = self.process_item(item)
                if record:
                    yield record
            logger.info(f"Page {page}: processed {len(items)} items")
            page += 1
            time.sleep(DELAY)

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield items modified since a given date."""
        page = 1
        while True:
            items = self.get_items(page=page)
            if not items:
                break
            for item in items:
                modified = item.get("o:modified", {}).get("@value", "")
                if modified and modified >= since:
                    record = self.process_item(item)
                    if record:
                        yield record
            page += 1
            time.sleep(DELAY)


def bootstrap_sample(max_records: int = 15):
    """Download a sample of laws for validation."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = AssembleeFetcher()
    count = 0

    # Sample from different parts of the collection
    sample_pages = [1, 20, 50, 80, 100]
    for page in sample_pages:
        if count >= max_records:
            break
        items = fetcher.get_items(page=page, per_page=5)
        for item in items:
            if count >= max_records:
                break
            record = fetcher.process_item(item)
            if not record:
                continue
            count += 1
            safe_id = re.sub(r"[^\w\-]", "_", record["_id"])
            out_path = SAMPLE_DIR / f"{safe_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            logger.info(
                f"[{count}/{max_records}] Saved {safe_id} "
                f"(text: {len(record['text'])} chars, date: {record.get('date')})"
            )

    logger.info(f"Sample complete: {count} records saved")


def main():
    parser = argparse.ArgumentParser(description="BJ/Assemblee bootstrapper")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "updates"],
        help="bootstrap = full fetch or sample; updates = incremental",
    )
    parser.add_argument("--sample", action="store_true", help="Only fetch a small sample")
    parser.add_argument("--max-records", type=int, default=15, help="Max records for sample mode")
    parser.add_argument("--since", type=str, default=None, help="ISO date for incremental updates")
    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample:
            bootstrap_sample(max_records=args.max_records)
        else:
            # Full mode: stream every record to data/records.jsonl (one JSON per
            # line) so ingest reads the full dataset, not just the sample subset.
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            jsonl_path = DATA_DIR / "records.jsonl"
            fetcher = AssembleeFetcher()
            count = 0
            seen = set()
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in fetcher.fetch_all():
                    rid = record.get("_id")
                    if rid in seen:
                        continue
                    seen.add(rid)
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 20 == 0:
                        logger.info(f"Fetched {count} records...")
            logger.info(f"Bootstrap complete: {count} total records -> {jsonl_path}")
    elif args.command == "updates":
        since = args.since or "2025-01-01"
        fetcher = AssembleeFetcher()
        count = 0
        for record in fetcher.fetch_updates(since):
            count += 1
        logger.info(f"Updates complete: {count} new records since {since}")


if __name__ == "__main__":
    main()
