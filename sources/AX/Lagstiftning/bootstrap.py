#!/usr/bin/env python3
"""
Åland Islands Legislation (Ålex) Data Fetcher

Fetches consolidated legislation from the Åland Islands government website.
Ålex contains ~517 consolidated laws with amendments incorporated into the text.

Source: https://www.regeringen.ax/alandsk-lagstiftning/alex
Language: Swedish
No authentication required.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.regeringen.ax"
LISTING_URL = f"{BASE_URL}/alandsk-lagstiftning/alex"
SOURCE_ID = "AX/Lagstiftning"
SAMPLE_DIR = Path(__file__).parent / "sample"


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sv,en;q=0.9",
    })
    return session


def strip_html(html: str) -> str:
    """Remove HTML tags and clean up whitespace."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    # Normalize whitespace but preserve paragraph breaks
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
        elif lines and lines[-1] != "":
            lines.append("")
    text = "\n".join(lines).strip()
    return text


def extract_law_ids_from_page(html: str) -> list[str]:
    """Extract Ålex law IDs from a listing page."""
    return re.findall(r'href="/alandsk-lagstiftning/alex/(\d+)"', html)


def parse_reference(title: str) -> Optional[str]:
    """Extract the reference number like '2025:59' from the title."""
    m = re.search(r"\((\d{4}:\d+)\)", title)
    return m.group(1) if m else None


def parse_law_type(title: str) -> str:
    """Extract law type from title (e.g. Landskapslag, Landskapsförordning)."""
    lower = title.lower()
    if "landskapslag" in lower:
        return "landskapslag"
    elif "landskapsförordning" in lower:
        return "landskapsförordning"
    elif "republikens presidents förordning" in lower:
        return "republikens_presidents_förordning"
    elif "lag " in lower or lower.startswith("lag"):
        return "lag"
    elif "förordning" in lower:
        return "förordning"
    return "unknown"


def parse_law_page(html: str, alex_id: str, url: str) -> Optional[Dict[str, Any]]:
    """Parse a single law page and extract structured data."""
    # Extract title from <h1> tag
    m = re.search(r'<h1[^>]*class="page-title"[^>]*>\s*(.*?)\s*</h1>', html, re.DOTALL)
    if not m:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if not m:
        logger.warning(f"No title found for {alex_id}")
        return None
    title = strip_html(m.group(1)).strip()

    # Extract the content-body div
    m = re.search(r'<div\s+class="content-body">(.*?)(?:</div>\s*</div>\s*</div>\s*<div\s+class="sidebar|$)',
                  html, re.DOTALL)
    if not m:
        # Fallback: try broader match
        m = re.search(r'<div\s+class="content-body">(.*)', html, re.DOTALL)
    if not m:
        logger.warning(f"No content-body found for {alex_id}")
        return None

    content_html = m.group(1)

    # Remove the sidebar and everything after it if present
    # The content-body ends before sidebar-related divs
    for cutoff in ['<div class="sidebar', '<div class="region region-sidebar',
                   '<div id="block-law-updated-toc', '<div class="law-updated-toc']:
        idx = content_html.find(cutoff)
        if idx > 0:
            content_html = content_html[:idx]

    text = strip_html(content_html)

    if len(text) < 20:
        logger.warning(f"Very short text ({len(text)} chars) for {alex_id}")
        return None

    reference = parse_reference(title)
    year = None
    if reference:
        year = reference.split(":")[0]

    # Extract date from meta or page
    date = None
    dm = re.search(r'"dateCreated"\s*:\s*"(\d{4}-\d{2}-\d{2})', html)
    if dm:
        date = dm.group(1)
    elif year:
        date = f"{year}-01-01"

    return {
        "_id": f"AX-alex-{alex_id}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "url": url,
        "alex_id": alex_id,
        "reference": reference,
        "law_type": parse_law_type(title),
        "year": year,
        "date": date,
        "language": "sv",
        "jurisdiction": "AX",
    }


def fetch_all_law_ids(session: requests.Session) -> list[str]:
    """Enumerate all Ålex law IDs by paginating through the listing."""
    all_ids = []
    page = 0
    while True:
        url = f"{LISTING_URL}?page={page}" if page > 0 else LISTING_URL
        logger.info(f"Fetching listing page {page}...")
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        ids = extract_law_ids_from_page(resp.text)
        if not ids:
            logger.info(f"No more laws on page {page}, done.")
            break
        all_ids.extend(ids)
        logger.info(f"  Page {page}: {len(ids)} laws (total: {len(all_ids)})")
        page += 1
        time.sleep(1.5)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for id_ in all_ids:
        if id_ not in seen:
            seen.add(id_)
            unique.append(id_)
    return unique


def fetch_all(session: requests.Session, sample_mode: bool = False, limit: int = 15) -> Iterator[Dict[str, Any]]:
    """Fetch all Ålex consolidated laws."""
    law_ids = fetch_all_law_ids(session)
    logger.info(f"Found {len(law_ids)} unique law IDs")

    if sample_mode:
        # Take a representative sample: some from start, middle, end
        if len(law_ids) > limit:
            step = len(law_ids) // limit
            law_ids = [law_ids[i * step] for i in range(limit)]
        law_ids = law_ids[:limit]
        logger.info(f"Sample mode: fetching {len(law_ids)} laws")

    fetched = 0
    errors = 0
    for i, alex_id in enumerate(law_ids):
        url = f"{LISTING_URL.replace('/alex', '')}/alex/{alex_id}"
        logger.info(f"[{i+1}/{len(law_ids)}] Fetching {alex_id}...")
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            record = parse_law_page(resp.text, alex_id, url)
            if record and len(record.get("text", "")) >= 20:
                fetched += 1
                yield record
            else:
                errors += 1
                logger.warning(f"  Skipped {alex_id}: insufficient text")
        except Exception as e:
            errors += 1
            logger.error(f"  Error fetching {alex_id}: {e}")
        time.sleep(2.0)

    logger.info(f"Done: {fetched} fetched, {errors} errors out of {len(law_ids)} total")


def normalize(record: Dict[str, Any]) -> Dict[str, Any]:
    """Already normalized during parse."""
    return record


def save_samples(records: list[Dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        fname = f"{rec['alex_id']}.json"
        path = output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(records)} samples to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Åland Islands Legislation (Ålex) Fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch only a sample of records")
    parser.add_argument("--full", action="store_true",
                        help="Fetch all records")
    parser.add_argument("--limit", type=int, default=15,
                        help="Number of sample records to fetch")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory for JSONL")
    args = parser.parse_args()

    session = create_session()
    sample_mode = args.sample or (not args.full)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for record in fetch_all(session, sample_mode=False):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        logger.info(f"Wrote {count} records to {output_path}")
    else:
        records = list(fetch_all(session, sample_mode=sample_mode, limit=args.limit))
        if records:
            save_samples(records, SAMPLE_DIR)
            # Print summary
            texts = [len(r.get("text", "")) for r in records]
            logger.info(f"Records: {len(records)}")
            logger.info(f"Text lengths: min={min(texts)}, max={max(texts)}, avg={sum(texts)//len(texts)}")
            for r in records[:3]:
                logger.info(f"  {r['alex_id']}: {r['title'][:80]}... ({len(r['text'])} chars)")
        else:
            logger.error("No records fetched!")
            sys.exit(1)


if __name__ == "__main__":
    main()
