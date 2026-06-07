#!/usr/bin/env python3
"""PW/FIC-Regulations — Palau Financial Institutions Commission.

Fetches laws and prudential regulations from ropfic.org.
PDFs are downloaded and text extracted via pdfminer.
"""

import argparse
import html
import json
import io
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from pdfminer.high_level import extract_text as _pdf_extract
except ImportError:
    _pdf_extract = None

SOURCE_ID = "PW/FIC-Regulations"
BASE_URL = "https://ropfic.org"
LAWS_PAGE = f"{BASE_URL}/laws-regulations/"
SAMPLE_DIR = Path(__file__).parent / "sample"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (legal-data-research)",
}

session = requests.Session()
session.headers.update(HEADERS)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer."""
    if _pdf_extract is None:
        raise ImportError("pdfminer.six is required: pip install pdfminer.six")
    return _pdf_extract(io.BytesIO(pdf_bytes))


def discover_documents():
    """Scrape the laws-regulations page and yield document metadata."""
    resp = session.get(LAWS_PAGE, timeout=30)
    resp.raise_for_status()
    html = resp.text

    # Find all PDF links on the page
    pdf_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*\.pdf)["\'][^>]*>([^<]*)</a>',
        re.IGNORECASE,
    )

    # Also find section headers to determine category
    section_pattern = re.compile(r'<h[2-4][^>]*>([^<]+)</h[2-4]>', re.IGNORECASE)
    sections = [(m.start(), m.group(1).strip()) for m in section_pattern.finditer(html)]

    seen_urls = set()
    for match in pdf_pattern.finditer(html):
        pdf_url = match.group(1).strip()
        link_text = match.group(2).strip()

        if not pdf_url or pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        # Make URL absolute
        if not pdf_url.startswith("http"):
            pdf_url = f"{BASE_URL}/{pdf_url.lstrip('/')}"

        # Determine category from nearest preceding section header
        pos = match.start()
        category = "other"
        for sec_pos, sec_name in reversed(sections):
            if sec_pos < pos:
                category = sec_name
                break

        # Derive a clean title from the link text or filename
        title = html.unescape(link_text) if link_text else Path(pdf_url).stem.replace("-", " ").replace("_", " ")

        # Generate a doc_id from the filename
        filename = Path(pdf_url).stem
        doc_id = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)

        yield {
            "doc_id": doc_id,
            "title": title,
            "pdf_url": pdf_url,
            "category": category,
        }


def normalize(raw: dict) -> dict:
    """Normalize a raw document into the standard schema."""
    now = datetime.now(timezone.utc).isoformat()
    doc_id = f"pw-fic-{raw['doc_id']}"
    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": now,
        "title": raw.get("title", ""),
        "text": raw.get("text", ""),
        "date": raw.get("date"),
        "url": LAWS_PAGE,
        "doc_id": doc_id,
        "category": raw.get("category", ""),
        "pdf_url": raw.get("pdf_url", ""),
    }


def fetch_all():
    """Yield all normalized documents."""
    for doc in discover_documents():
        try:
            print(f"  Fetching: {doc['title'][:60]}...", file=sys.stderr)
            resp = session.get(doc["pdf_url"], timeout=60)
            resp.raise_for_status()

            text = extract_text_from_pdf(resp.content)
            if len(text.strip()) < 50:
                print(f"  [SKIP] Insufficient text for {doc['title']}", file=sys.stderr)
                continue

            doc["text"] = text.strip()
            yield normalize(doc)
            time.sleep(1.5)
        except Exception as e:
            print(f"  [ERROR] {doc['title']}: {e}", file=sys.stderr)
            time.sleep(2)


def bootstrap_sample(limit: int = 15):
    """Fetch sample documents and save to sample/."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in fetch_all():
        if count >= limit:
            break
        fname = SAMPLE_DIR / f"record_{count:04d}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        text_len = len(record.get("text", ""))
        print(f"  [{count+1}/{limit}] {record['title'][:60]} ({text_len} chars)")
        count += 1

    print(f"\nSaved {count} samples to {SAMPLE_DIR}")
    return count


def main():
    parser = argparse.ArgumentParser(description="PW/FIC-Regulations bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Run bootstrapper")
    boot.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot.add_argument("--limit", type=int, default=15, help="Sample limit")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    args = parser.parse_args()

    if args.command == "bootstrap":
        if args.sample or not args.full:
            count = bootstrap_sample(args.limit)
            if count < 10:
                print(f"WARNING: Only {count} samples collected", file=sys.stderr)
                sys.exit(1)
        else:
            for record in fetch_all():
                print(json.dumps(record, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
