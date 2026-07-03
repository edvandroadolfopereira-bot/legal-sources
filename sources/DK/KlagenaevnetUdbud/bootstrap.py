#!/usr/bin/env python3
"""
DK/KlagenaevnetUdbud — Danish Complaints Board for Public Procurement.

Klagenævnet for Udbud (the Complaints Board for Public Procurement) is the
Danish administrative tribunal that decides complaints about public tenders.
It publishes, as a matter of principle, all of its final decisions (kendelser)
from 1995 to the present at https://klfu.naevneneshus.dk/.

Data access strategy:
  - The search portal is an Angular SPA backed by a public JSON API at
    POST https://klfu.naevneneshus.dk/api/search.
  - Each result record already contains the FULL decision text in the `body`
    field as HTML — no per-document fetch or PDF extraction is required.
  - Pagination is via skip/size; ~1,695 board rulings are available.

License: Public domain — Danish Copyright Act (Ophavsretsloven) § 9, which
excludes laws, administrative orders, court judgments and similar decisions
of public authorities from copyright protection.
"""

import argparse
import html
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.DK.KlagenaevnetUdbud")

SOURCE_ID = "DK/KlagenaevnetUdbud"
BASE_URL = "https://klfu.naevneneshus.dk"
SEARCH_URL = f"{BASE_URL}/api/search"
PORTAL_URL = f"{BASE_URL}/soeg?sort=desc&types=ruling"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"

PAGE_SIZE = 50


def html_to_text(raw_html: str) -> str:
    """Strip HTML tags and decode entities into clean plain text."""
    if not raw_html:
        return ""
    # Drop script/style blocks entirely.
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Turn block-level boundaries into newlines so paragraphs stay separated.
    text = re.sub(r"</(p|div|tr|h[1-6]|li|table)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Remove remaining tags.
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&aelig;, &oslash;, &nbsp;, ...).
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    # Collapse whitespace, preserving paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


class KlagenaevnetUdbudScraper:
    """Scraper for the Danish Complaints Board for Public Procurement."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "da,en;q=0.7",
        })

    def _search(self, skip: int, size: int) -> dict:
        payload = {
            "query": "",
            "types": ["ruling"],
            "skip": skip,
            "size": size,
            "sort": "Descending",
        }
        resp = self.session.post(SEARCH_URL, data=json.dumps(payload), timeout=60)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _first(value):
        """jnr/categories come back as lists; take the first meaningful value."""
        if isinstance(value, list):
            return value[0] if value else ""
        return value or ""

    def normalize(self, raw: dict) -> dict:
        """Transform a raw search record into the standard schema."""
        text = html_to_text(raw.get("body", ""))
        jnr = self._first(raw.get("jnr"))
        rec_id = raw.get("id", "")
        date = raw.get("date") or (raw.get("published_date") or "")[:10] or None
        url = f"{BASE_URL}/afgoerelse/{rec_id}" if rec_id else BASE_URL
        return {
            "_id": f"KLFU-{jnr or rec_id}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", "") or f"Kendelse {jnr}",
            "text": text,
            "date": date,
            "url": url,
            "case_number": jnr,
            "category": self._first(raw.get("categories")),
            "authority": raw.get("authority", "Klagenævnet for Udbud"),
            "abstract": html_to_text(raw.get("abstract", "")),
            "is_board_ruling": raw.get("is_board_ruling"),
            "is_brought_to_court": raw.get("is_brought_to_court"),
            "published_date": (raw.get("published_date") or "")[:10] or None,
            "language": "da",
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions with full text, paging through the API."""
        skip = 0
        total = None
        seen = set()
        while True:
            try:
                data = self._search(skip, PAGE_SIZE)
            except requests.RequestException as e:
                logger.error(f"Search request failed at skip={skip}: {e}")
                break
            if total is None:
                total = data.get("totalCount", 0)
                logger.info(f"Total rulings available: {total}")
            pubs = data.get("publications", [])
            if not pubs:
                break
            for raw in pubs:
                rid = raw.get("id")
                if rid in seen:
                    continue
                seen.add(rid)
                yield self.normalize(raw)
            skip += PAGE_SIZE
            if skip >= (total or 0):
                break
            time.sleep(1)

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """Yield recent decisions newer than `since` (ISO date)."""
        since_date = None
        if since:
            since_date = since[:10]
        for rec in self.fetch_all():
            if since_date and rec.get("date") and rec["date"] < since_date:
                break  # results are sorted newest-first
            yield rec

    def test(self) -> bool:
        """Smoke test: confirm the API returns rulings with full text."""
        try:
            data = self._search(0, 3)
        except requests.RequestException as e:
            logger.error(f"API unreachable: {e}")
            return False
        pubs = data.get("publications", [])
        logger.info(f"API OK — totalCount={data.get('totalCount')}, page returned {len(pubs)} rulings")
        if pubs:
            sample = self.normalize(pubs[0])
            logger.info(f"Sample: {sample['_id']} — {len(sample['text']):,} chars text")
            return len(sample["text"]) > 100
        return False


def main():
    parser = argparse.ArgumentParser(description="DK/KlagenaevnetUdbud data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch a small sample (15 records)")
    parser.add_argument("--full", action="store_true", help="Fetch all records to data/records.jsonl")
    args = parser.parse_args()

    scraper = KlagenaevnetUdbudScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)
        return

    if args.command == "update":
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for record in scraper.fetch_updates():
            out_path = SAMPLE_DIR / f"update_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
            if count >= 50:
                break
        logger.info(f"Update complete: {count} records")
        return

    # bootstrap / bootstrap-fast
    full = args.full or args.command == "bootstrap-fast"
    if args.sample:
        full = False

    if full:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / "records.jsonl"
        count = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for record in scraper.fetch_all():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                if count % 100 == 0:
                    logger.info(f"  ... {count} records written")
        logger.info(f"Bootstrap complete: {count} records -> {out_path}")
        return

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    max_records = 15
    for record in scraper.fetch_all():
        out_path = SAMPLE_DIR / f"record_{count:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[{count + 1}] {record.get('case_number', '?')} "
            f"{record.get('title', '?')[:60]} ({len(record.get('text', '')):,} chars)"
        )
        count += 1
        if count >= max_records:
            break
    logger.info(f"Bootstrap complete: {count} records saved to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
