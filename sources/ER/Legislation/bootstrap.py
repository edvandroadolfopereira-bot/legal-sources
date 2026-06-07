#!/usr/bin/env python3
"""
ER/Legislation -- Gazette of Eritrean Laws from the Library of Congress

Fetches Eritrean proclamations and legal notices (1991-2022) from the LOC
Foreign Legal Gazettes digital collection via the public JSON API.

Strategy:
  1. Paginate through the LOC JSON API for Eritrean gazette items
  2. Download each item's PDF and extract text via common.pdf_extract
  3. Only emit records where full text extraction succeeds (skip scanned-only PDFs)

The collection contains ~390 items. Roughly 10-20% have born-digital PDFs
with extractable text; the rest are scanned images requiring OCR.

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py bootstrap-fast
  python bootstrap.py test
"""

import argparse
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

from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.ER.Legislation")

SOURCE_ID = "ER/Legislation"
LOC_COLLECTION_URL = "https://www.loc.gov/collections/foreign-legal-gazettes/"
DELAY = 2.0
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "LegalDataHunter/1.0 (legal research; +https://legaldatahunter.com)"
})


def _fetch_all_items() -> List[Dict]:
    """Paginate through LOC JSON API to get all Eritrean gazette items."""
    items: List[Dict] = []
    for page in range(1, 20):
        url = f"{LOC_COLLECTION_URL}?q=eritrea&fo=json&c=50&sp={page}"
        logger.info("Fetching LOC page %d...", page)
        try:
            resp = SESSION.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Failed to fetch LOC page %d: %s", page, e)
            break

        results = data.get("results", [])
        if not results:
            break

        items.extend(results)
        logger.info("Page %d: %d items (total: %d)", page, len(results), len(items))

        if data.get("pagination", {}).get("next") is None:
            break
        time.sleep(DELAY)

    return items


def _extract_item_id(loc_id: str) -> str:
    """Extract a clean ID from the LOC item URL.
    e.g. 'http://www.loc.gov/item/eritrean-proc-21-1992/' -> 'eritrean-proc-21-1992'
    """
    return loc_id.rstrip("/").split("/")[-1]


def _get_pdf_url(item: Dict) -> Optional[str]:
    """Extract the PDF URL from an item's resources array."""
    for resource in item.get("resources", []):
        pdf = resource.get("pdf")
        if pdf:
            return pdf
    return None


def _extract_date(item: Dict) -> Optional[str]:
    """Extract and validate the date from an item."""
    date = item.get("date")
    if date and re.match(r"\d{4}-\d{2}-\d{2}", date):
        return date
    # Try to extract year from dates array
    dates = item.get("dates", [])
    for d in dates:
        if isinstance(d, str) and re.match(r"\d{4}", d):
            return d
    return date


def _extract_subjects(item: Dict) -> List[str]:
    """Extract subject terms from an item."""
    subjects = item.get("subject", [])
    if isinstance(subjects, list):
        return [s for s in subjects if isinstance(s, str)]
    return []


def _determine_doc_type(title: str) -> str:
    """Determine whether this is a proclamation or legal notice."""
    title_lower = title.lower()
    if "proclamation" in title_lower:
        return "proclamation"
    elif "notice" in title_lower or "regulation" in title_lower:
        return "legal_notice"
    elif "code" in title_lower:
        return "code"
    return "legislation"


def normalize(item: Dict, text: str) -> Dict:
    """Transform a LOC item + extracted text into a normalized record."""
    item_id = _extract_item_id(item.get("id", ""))
    title = item.get("title", "Untitled")
    date = _extract_date(item)
    url = item.get("url", item.get("id", ""))
    languages = item.get("language", [])
    subjects = _extract_subjects(item)
    doc_type = _determine_doc_type(title)

    return {
        "_id": item_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": date,
        "url": url,
        "language": languages,
        "subjects": subjects,
        "document_type": doc_type,
        "publisher": "Government of the State of Eritrea",
        "collection": "Gazette of Eritrean Laws",
        "digitized_by": "Library of Congress",
        "pdf_url": _get_pdf_url(item),
    }


def fetch_all(sample: bool = False) -> Generator[Dict, None, None]:
    """Fetch all Eritrean legislation from LOC, extract PDF text, yield records."""
    items = _fetch_all_items()
    logger.info("Found %d LOC items for Eritrea", len(items))

    yielded = 0
    skipped_no_pdf = 0
    skipped_no_text = 0

    for i, item in enumerate(items):
        if sample and yielded >= 15:
            break

        title = item.get("title", "Untitled")
        pdf_url = _get_pdf_url(item)

        if not pdf_url:
            skipped_no_pdf += 1
            logger.debug("No PDF for: %s", title)
            continue

        item_id = _extract_item_id(item.get("id", ""))
        logger.info("[%d/%d] Processing: %s", i + 1, len(items), title[:80])

        text = extract_pdf_markdown(
            source=SOURCE_ID,
            source_id=item_id,
            pdf_url=pdf_url,
            table="legislation",
            force=True,
        )

        if not text or len(text.strip()) < 50:
            skipped_no_text += 1
            logger.info("  -> No extractable text (scanned PDF), skipping")
            continue

        record = normalize(item, text)
        yielded += 1
        logger.info(
            "  -> OK: %d chars, %s (%d/%d)",
            len(text), item_id, yielded, len(items)
        )
        yield record

        time.sleep(DELAY)

    logger.info(
        "Done: %d records yielded, %d skipped (no PDF), %d skipped (no text)",
        yielded, skipped_no_pdf, skipped_no_text,
    )


def run_bootstrap(sample: bool = False):
    """Run the bootstrap and save results."""
    source_dir = Path(__file__).resolve().parent
    sample_dir = source_dir / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    for record in fetch_all(sample=sample):
        count += 1
        fname = f"{record['_id']}.json"
        out = sample_dir / fname
        with open(out, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        logger.info("Saved: %s", out.name)

    logger.info("Bootstrap complete: %d records saved to %s", count, sample_dir)
    return count


def run_test():
    """Quick smoke test: fetch metadata for first page, no PDFs."""
    items = _fetch_all_items()
    print(f"Total items: {len(items)}")
    with_pdf = sum(1 for i in items if _get_pdf_url(i))
    print(f"Items with PDF: {with_pdf}")
    if items:
        sample = items[0]
        print(f"Sample title: {sample.get('title')}")
        print(f"Sample date: {sample.get('date')}")
        print(f"Sample PDF: {_get_pdf_url(sample)}")
    return len(items) > 0


def main():
    parser = argparse.ArgumentParser(description="ER/Legislation bootstrap")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Only fetch 15 samples")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    if args.command == "test":
        success = run_test()
        sys.exit(0 if success else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = args.sample or (not args.full)
        count = run_bootstrap(sample=sample_mode)
        sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()
