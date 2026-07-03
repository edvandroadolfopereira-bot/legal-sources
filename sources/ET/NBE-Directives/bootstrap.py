#!/usr/bin/env python3
"""ET/NBE-Directives — Ethiopia National Bank Directives.

Uses WordPress REST API to list directives, extracts PDF URLs from
spectra_custom_meta.file_url, and downloads + extracts text.
"""

import argparse
import html as htmlmod
import io
import json
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

SOURCE_ID = "ET/NBE-Directives"
API_URL = "https://nbe.gov.et/wp-json/wp/v2/files"
SAMPLE_DIR = Path(__file__).parent / "sample"

session = requests.Session()
session.headers.update({
    "User-Agent": "LegalDataHunter/1.0 (legal-data-research)",
    "Accept": "application/json",
})


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if _pdf_extract is None:
        raise ImportError("pdfminer.six required: pip install pdfminer.six")
    return _pdf_extract(io.BytesIO(pdf_bytes))


def list_files(per_page: int = 20):
    """Yield all file posts from the WP REST API."""
    page = 1
    while True:
        resp = session.get(API_URL, params={
            "per_page": per_page,
            "page": page,
        }, timeout=30)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        yield from data
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(1)


def get_pdf_url(post: dict) -> str:
    """Extract PDF URL from spectra_custom_meta or content."""
    meta = post.get("spectra_custom_meta", {})
    if isinstance(meta, dict):
        file_url = meta.get("file_url")
        if file_url:
            if isinstance(file_url, list):
                file_url = file_url[0]
            return file_url

    # Fallback: check content for PDF links
    content = post.get("content", {}).get("rendered", "")
    pdfs = re.findall(r'href="([^"]+\.pdf)"', content)
    return pdfs[0] if pdfs else None


def normalize(post: dict, text: str) -> dict:
    title = htmlmod.unescape(post.get("title", {}).get("rendered", ""))
    date_str = post.get("date", "")[:10] if post.get("date") else None
    link = post.get("link", "")
    pdf_url = get_pdf_url(post) or ""
    doc_id = f"et-nbe-{post['id']}"

    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": date_str,
        "url": link,
        "doc_id": doc_id,
        "pdf_url": pdf_url,
        "directive_number": title.split("–")[0].split("—")[0].strip() if "–" in title or "—" in title else title,
    }


def fetch_all():
    """Yield all normalized directives."""
    for post in list_files():
        pdf_url = get_pdf_url(post)
        if not pdf_url:
            title = post.get("title", {}).get("rendered", "?")
            print(f"  [SKIP] No PDF for {title[:50]}", file=sys.stderr)
            continue

        try:
            resp = session.get(pdf_url, timeout=60)
            resp.raise_for_status()
            text = extract_text_from_pdf(resp.content)
            if len(text.strip()) < 50:
                print(f"  [SKIP] Insufficient text from {pdf_url}", file=sys.stderr)
                continue
            yield normalize(post, text)
            time.sleep(1.5)
        except Exception as e:
            print(f"  [ERROR] {pdf_url}: {e}", file=sys.stderr)
            time.sleep(2)


def bootstrap_sample(limit: int = 15):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in fetch_all():
        if count >= limit:
            break
        fname = SAMPLE_DIR / f"{record['_id']}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        text_len = len(record.get("text", ""))
        print(f"  [{count+1}/{limit}] {record['title'][:60]} ({text_len} chars)")
        count += 1
    print(f"\nSaved {count} samples to {SAMPLE_DIR}")
    return count


def main():
    parser = argparse.ArgumentParser(description="ET/NBE-Directives bootstrap")
    sub = parser.add_subparsers(dest="command")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--sample", action="store_true")
    boot.add_argument("--limit", type=int, default=15)
    boot.add_argument("--full", action="store_true")
    # bootstrap-fast: VPS pipeline alias — streams the full corpus to JSONL
    fast = sub.add_parser("bootstrap-fast")
    fast.add_argument("--full", action="store_true")
    args = parser.parse_args()

    if args.command == "bootstrap-fast" or (args.command == "bootstrap" and getattr(args, "full", False)):
        # Stream every directive to data/records.jsonl so the ingest pipeline
        # picks up the full corpus, not just the pre-existing sample/ files.
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = data_dir / "records.jsonl"
        count = 0
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for record in fetch_all():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                if count % 25 == 0:
                    print(f"Progress: {count} records written", file=sys.stderr)
        print(f"Wrote {count} records -> {jsonl_path}", file=sys.stderr)
    elif args.command == "bootstrap":
        count = bootstrap_sample(args.limit)
        if count < 10:
            print(f"WARNING: Only {count} samples", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
