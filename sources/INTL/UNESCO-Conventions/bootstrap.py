#!/usr/bin/env python3
"""
INTL/UNESCO-Conventions — UNESCO Legal Instruments

Fetches conventions, recommendations, and declarations from UNESCO DataHub API.

Strategy:
  - Use UNESCO DataHub ODSQL API (data.unesco.org) to fetch all 94 records
  - Each record contains full text in English, French, and Spanish
  - Single paginated API call, no HTML scraping needed

Data:
  - 94 legal instruments (conventions, recommendations, declarations)
  - Languages: English, French, Spanish
  - License: UNESCO open access

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://data.unesco.org/api/explore/v2.1/catalog/datasets/la0001/records"
SOURCE_ID = "INTL/UNESCO-Conventions"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"
JSONL_PATH = DATA_DIR / "records.jsonl"
REQUEST_DELAY = 1.0


class UNESCOConventionsFetcher:
    """Fetcher for UNESCO legal instruments via DataHub API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def _fetch_page(self, offset: int = 0, limit: int = 100) -> Optional[dict]:
        """Fetch a page of records from the API."""
        time.sleep(REQUEST_DELAY)
        params = {"limit": limit, "offset": offset}
        for attempt in range(3):
            try:
                resp = self.session.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < 2:
                    logger.warning("Retry %d: %s", attempt + 1, e)
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.error("Failed to fetch API: %s", e)
                    return None

    def normalize(self, record: dict) -> Optional[Dict[str, Any]]:
        """Normalize an API record into standard schema."""
        fields = record.get("record", {}).get("fields", record)
        if "fields" in record and isinstance(record["fields"], dict):
            fields = record["fields"]

        title = (fields.get("title_en") or "").strip()
        if not title:
            title = (fields.get("title_fr") or "").strip()
        if not title:
            return None

        # Build full text from all language versions.
        # The API returns optional language keys present but with value null,
        # so the .get(key, "") default never applies — coalesce None explicitly.
        text_parts = []
        intro_en = (fields.get("introduction_en") or "").strip()
        if intro_en:
            text_parts.append(intro_en)

        intro_fr = (fields.get("introduction_fr") or "").strip()
        if intro_fr and intro_fr != intro_en:
            text_parts.append(f"\n\n--- Version française ---\n\n{intro_fr}")

        intro_es = (fields.get("introduction_es") or "").strip()
        if intro_es and intro_es != intro_en:
            text_parts.append(f"\n\n--- Versión española ---\n\n{intro_es}")

        text = "\n".join(text_parts)
        if not text or len(text) < 100:
            return None

        date_str = fields.get("date") or ""
        doc_id_num = fields.get("id") or fields.get("uuid") or ""
        slug = title[:60].replace(" ", "-").replace("/", "-").lower()
        doc_id = f"UNESCO-{doc_id_num}-{slug}" if doc_id_num else f"UNESCO-{slug}"

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "title_fr": fields.get("title_fr") or "",
            "title_es": fields.get("title_es") or "",
            "text": text,
            "date": date_str[:10] if date_str else None,
            "url": f"https://www.unesco.org/en/legal-affairs/standard-setting/conventions",
        }

    def fetch_all(self, sample: bool = False, max_docs: int = 15) -> Iterator[Dict[str, Any]]:
        """Yield all UNESCO legal instruments."""
        offset = 0
        count = 0
        total = None

        while True:
            data = self._fetch_page(offset=offset, limit=100)
            if not data:
                break

            if total is None:
                total = data.get("total_count", 0)
                logger.info("Total records in API: %d", total)

            records = data.get("results", data.get("records", []))
            if not records:
                break

            for rec in records:
                doc = self.normalize(rec)
                if doc:
                    count += 1
                    yield doc

                if sample and count >= max_docs:
                    return

            offset += len(records)
            if offset >= (total or 0):
                break

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield all instruments (no date filtering in API)."""
        yield from self.fetch_all()


def bootstrap(sample: bool = False, full: bool = False, since: Optional[str] = None):
    """Main entry point."""
    fetcher = UNESCOConventionsFetcher()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    if since:
        docs = fetcher.fetch_updates(since)
    else:
        docs = fetcher.fetch_all(sample=sample)

    # In full (non-sample) mode, stream every record to data/records.jsonl so
    # the VPS ingest pipeline can pick them up. In sample mode, write sample/*.json.
    jsonl_f = None
    if not sample:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        jsonl_f = open(JSONL_PATH, "w", encoding="utf-8")

    count = 0
    try:
        for doc in docs:
            count += 1
            text_len = len(doc.get("text", ""))
            logger.info("  → %s | text=%d chars | date=%s", doc["title"][:70], text_len, doc.get("date"))

            if sample:
                sample_path = SAMPLE_DIR / f"{doc['_id']}.json"
                with open(sample_path, "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=2)
            else:
                jsonl_f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    finally:
        if jsonl_f:
            jsonl_f.close()

    logger.info("Done: %d instruments fetched", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="INTL/UNESCO-Conventions bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast"], help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Save sample records")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    parser.add_argument("--since", type=str, help="Fetch updates since date (ISO 8601)")
    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        count = bootstrap(sample=args.sample, full=args.full, since=args.since)
        if count == 0:
            logger.error("No records fetched!")
            sys.exit(1)
