#!/usr/bin/env python3
"""
INTL/INTERPOL-CCF — INTERPOL Commission for the Control of Files decisions.

Fetches anonymized decision excerpts published by INTERPOL's CCF (2017–2025).
The CCF is a quasi-judicial oversight body that reviews complaints about data
processed through INTERPOL's systems (Red Notices, diffusions, etc.).

Data source: https://www.interpol.int/en/Who-we-are/Commission-for-the-Control-of-INTERPOL-s-Files-CCF/CCF-sessions-and-decisions
Method:      HTML scrape for PDF links → PDF download → pdfminer text extraction
License:     INTERPOL website terms (public information)

Usage:
  python bootstrap.py bootstrap --sample   # Fetch ~15 sample records
  python bootstrap.py bootstrap            # Full bootstrap
  python bootstrap.py bootstrap --full     # Alias for full bootstrap
  python bootstrap.py bootstrap-fast       # VPS pipeline alias
  python bootstrap.py test                 # Test connectivity
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import unquote

import requests

SOURCE_ID = "INTL/INTERPOL-CCF"
SAMPLE_DIR = Path(__file__).parent / "sample"

INDEX_URL = (
    "https://www.interpol.int/en/Who-we-are/"
    "Commission-for-the-Control-of-INTERPOL-s-Files-CCF/"
    "CCF-sessions-and-decisions"
)

DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_pdf_links(session: requests.Session) -> list[dict]:
    """Scrape the CCF sessions page and extract all decision excerpt PDF links."""
    resp = session.get(INDEX_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    # Find all PDF hrefs
    raw_links = re.findall(r'href="([^"]+\.pdf)"', html)

    seen = set()
    decisions = []
    for href in raw_links:
        clean = href.split("?")[0].replace("&amp;", "&")
        if clean in seen:
            continue
        seen.add(clean)

        decoded = unquote(clean)
        # Only keep "Decision Excerpt" PDFs (skip budget docs, table of contents)
        if "Decision Excerpt" not in decoded:
            continue
        # Skip the "Table of contents" aggregate PDF
        if "Table of contents" in decoded:
            continue

        meta = parse_filename_metadata(decoded)
        decisions.append({"url": clean, "decoded_filename": decoded, **meta})

    return decisions


def parse_filename_metadata(decoded_url: str) -> dict:
    """Extract year, number, and topics from the PDF filename."""
    filename = decoded_url.rsplit("/", 1)[-1]
    # Remove .pdf extension
    name = filename.replace(".pdf", "").strip()

    # Extract year (first 4 digits)
    year_match = re.search(r"(\d{4})", name)
    year = year_match.group(1) if year_match else None

    # Extract decision number — patterns like N°01, N°1, N° 6
    num_match = re.search(r"N°\s*(\d+)", name)
    number = int(num_match.group(1)) if num_match else None

    # Extract topics — everything after the number and dash
    topics = ""
    topic_match = re.search(r"N°\s*\d+\s*[-–—]\s*(.+)$", name)
    if not topic_match:
        # Some files like "N°14.pdf" have no topic
        topic_match = re.search(r"N°\s*\d+\s*$", name)
    if topic_match and topic_match.lastindex:
        topics = topic_match.group(1).strip().rstrip(".")

    return {"year": year, "number": number, "topics": topics}


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer."""
    from pdfminer.high_level import extract_text
    import io

    text = extract_text(io.BytesIO(pdf_bytes))
    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def download_pdf(url: str, session: requests.Session) -> Optional[bytes]:
    """Download a PDF and return its bytes."""
    for attempt in range(3):
        try:
            resp = session.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200 and resp.content:
                ct = resp.headers.get("Content-Type", "")
                if "pdf" in ct or resp.content[:5] == b"%PDF-":
                    return resp.content
                print(f"  Warning: expected PDF but got {ct}")
                return None
            if resp.status_code >= 500:
                print(f"  HTTP {resp.status_code}, retrying ({attempt + 1}/3)...")
                time.sleep(DELAY * 2)
                continue
            print(f"  HTTP {resp.status_code} for {url}")
            return None
        except requests.RequestException as e:
            print(f"  Request error ({attempt + 1}/3): {e}")
            time.sleep(DELAY * 2)
    return None


def make_id(year: str, number: int) -> str:
    """Create a stable document ID."""
    return f"ccf-decision-{year}-{number:02d}"


def normalize(raw: dict) -> dict:
    """Transform a raw record into the standard schema."""
    year = raw.get("year", "unknown")
    number = raw.get("number", 0)
    topics = raw.get("topics", "")

    title_parts = [f"CCF Decision Excerpt {year} N°{number}"]
    if topics:
        title_parts.append(f"— {topics}")
    title = " ".join(title_parts)

    return {
        "_id": make_id(year, number),
        "_source": SOURCE_ID,
        "_type": "case_law",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": raw.get("text", ""),
        "date": f"{year}-01-01" if year else None,
        "url": raw.get("url", ""),
        "year": year,
        "decision_number": number,
        "topics": topics,
        "body": "INTERPOL Commission for the Control of Files",
    }


def fetch_all(
    session: requests.Session, sample: bool = False
) -> Generator[dict, None, None]:
    """Fetch all CCF decision excerpts."""
    print(f"Fetching CCF decision links from {INDEX_URL}...")
    decisions = extract_pdf_links(session)
    print(f"Found {len(decisions)} decision excerpt PDFs")

    if sample:
        decisions = decisions[:15]
        print(f"Sample mode: processing first {len(decisions)} decisions")

    for i, dec in enumerate(decisions, 1):
        url = dec["url"]
        decoded = dec.get("decoded_filename", url)
        print(f"[{i}/{len(decisions)}] Downloading: {decoded.rsplit('/', 1)[-1]}")

        pdf_bytes = download_pdf(url, session)
        if not pdf_bytes:
            print(f"  Skipped (download failed)")
            continue

        try:
            text = extract_text_from_pdf(pdf_bytes)
        except Exception as e:
            print(f"  PDF text extraction failed: {e}")
            continue

        if len(text) < 100:
            print(f"  Skipped (text too short: {len(text)} chars)")
            continue

        raw = {**dec, "text": text}
        record = normalize(raw)
        print(f"  OK: {len(text)} chars")
        yield record

        time.sleep(DELAY)


def save_sample(record: dict, sample_dir: Path):
    """Save a record to the sample directory."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{record['_id']}.json"
    path = sample_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def cmd_bootstrap(args):
    """Run the bootstrap process."""
    sample = getattr(args, "sample", False)
    session = requests.Session()

    count = 0
    for record in fetch_all(session, sample=sample):
        if sample:
            save_sample(record, SAMPLE_DIR)
        else:
            print(json.dumps(record, ensure_ascii=False))
        count += 1

    print(f"\nDone. {count} records {'saved to sample/' if sample else 'emitted'}.")
    return 0 if count > 0 else 1


def cmd_test(args):
    """Test connectivity to the INTERPOL CCF page."""
    session = requests.Session()
    try:
        resp = session.get(INDEX_URL, headers=HEADERS, timeout=15)
        print(f"HTTP {resp.status_code} — {len(resp.text)} bytes")
        decisions = extract_pdf_links(session)
        print(f"Found {len(decisions)} decision excerpt PDFs")

        if decisions:
            first = decisions[0]
            print(f"Testing first PDF: {first['decoded_filename'].rsplit('/', 1)[-1]}")
            pdf_bytes = download_pdf(first["url"], session)
            if pdf_bytes:
                text = extract_text_from_pdf(pdf_bytes)
                print(f"  PDF text: {len(text)} chars")
                print(f"  Preview: {text[:200]}...")
                return 0
            else:
                print("  Failed to download PDF")
                return 1
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="INTL/INTERPOL-CCF bootstrap")
    sub = parser.add_subparsers(dest="command")

    bp = sub.add_parser("bootstrap", help="Run bootstrap")
    bp.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    bp.add_argument("--full", action="store_true", help="Full mode (ignored, default)")
    bp.set_defaults(func=cmd_bootstrap)

    # VPS pipeline alias
    bf = sub.add_parser("bootstrap-fast", help="VPS pipeline alias for bootstrap")
    bf.add_argument("--sample", action="store_true")
    bf.set_defaults(func=cmd_bootstrap)

    tp = sub.add_parser("test", help="Test connectivity")
    tp.set_defaults(func=cmd_test)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
