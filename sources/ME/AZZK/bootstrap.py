#!/usr/bin/env python3
"""
Montenegro Agency for Protection of Competition (AZZK) decisions fetcher.

Fetches competition enforcement decisions from azzk.me.
Categories: mergers, restrictive agreements, abuse of dominant position, opinions.
All documents are PDFs with extractable text (Montenegrin/Serbian).
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.pdf_extract import extract_pdf_markdown

BASE_URL = "https://azzk.me"
REQUEST_DELAY = 2.0

# Decision category pages with their types
DECISION_PAGES = [
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2022/",
        "type": "merger",
        "label": "Mergers 2022",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2021/",
        "type": "merger",
        "label": "Mergers 2021",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2020/",
        "type": "merger",
        "label": "Mergers 2020",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2017-2019/",
        "type": "merger",
        "label": "Mergers 2017-2019",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2010-2012/",
        "type": "merger",
        "label": "Mergers 2010-2012",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/solutions-for-2006-2009/",
        "type": "merger",
        "label": "Mergers 2006-2009",
    },
    {
        "url": "/en/protection-of-competition/decisions/merges/",
        "type": "merger_suspension",
        "label": "Merger Suspensions/Rejections",
    },
    {
        "url": "/en/protection-of-competition/decisions/restrictive-agreements/",
        "type": "restrictive_agreement",
        "label": "Restrictive Agreements",
    },
    {
        "url": "/en/protection-of-competition/decisions/abuse-of-dominant-position/",
        "type": "abuse_of_dominance",
        "label": "Abuse of Dominant Position",
    },
    {
        "url": "/en/protection-of-competition/decisions/opinions/",
        "type": "opinion",
        "label": "Opinions",
    },
    {
        "url": "/en/protection-of-competition/decisions/individual-exemptions/",
        "type": "individual_exemption",
        "label": "Individual Exemptions",
    },
]


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal research project)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,sr;q=0.5",
    })
    return session


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract date from filename or link text like '04022022' or '04.02.2022'."""
    # Pattern: DDMMYYYY in filename
    m = re.search(r'(\d{2})(\d{2})(20\d{2})', text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"

    # Pattern: DD.MM.YYYY in text
    m = re.search(r'(\d{2})\.(\d{2})\.(20\d{2})', text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"

    # Pattern: DDMM in filename (no year context)
    m = re.search(r'_(\d{4})\.pdf$', text)
    if m:
        digits = m.group(1)
        day, month = digits[:2], digits[2:]
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return None  # Can't determine year from just DDMM

    return None


def extract_year_from_context(filename: str, page_label: str) -> Optional[str]:
    """Extract year from filename or page context."""
    # Try date from filename
    m = re.search(r'(20\d{2})', filename)
    if m:
        return m.group(1)

    # From page label like "Mergers 2021"
    m = re.search(r'(20\d{2})', page_label)
    if m:
        return m.group(1)

    # Year range from label like "2017-2019"
    m = re.search(r'(20\d{2})-(20\d{2})', page_label)
    if m:
        return m.group(2)  # Use latest year

    return None


def parse_pdf_links(session: requests.Session, page_url: str,
                    decision_type: str, page_label: str) -> list[dict]:
    """Parse a page and extract all PDF links."""
    try:
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed to fetch {page_url}: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.lower().endswith(".pdf"):
            continue

        # Normalize the URL - handle jml.test dev URLs
        if "jml.test" in href:
            # Extract just the filename path
            path = re.sub(r'^https?://jml\.test/images', '', href)
            pdf_url = f"{BASE_URL}{path}"
        elif href.startswith("http"):
            pdf_url = href
        elif href.startswith("/"):
            pdf_url = f"{BASE_URL}{href}"
        else:
            pdf_url = f"{BASE_URL}/{href}"

        if pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        # Get title from link text or parent
        title = link.get_text(strip=True)
        if not title or title.endswith(".pdf"):
            parent = link.parent
            if parent:
                title = parent.get_text(strip=True)

        # Clean title
        title = re.sub(r'\s+', ' ', title).strip() if title else ""
        if not title:
            title = unquote(Path(href).stem).replace("_", " ").replace("-", " ")

        # Extract date
        filename = unquote(href.split("/")[-1])
        date = extract_date_from_text(filename)
        if not date:
            # Try the text next to the link
            parent_text = link.parent.get_text() if link.parent else ""
            date = extract_date_from_text(parent_text)

        # At minimum get year
        year = None
        if date:
            year = date[:4]
        else:
            year = extract_year_from_context(filename, page_label)
            if year:
                date = f"{year}-01-01"

        results.append({
            "title": title,
            "pdf_url": pdf_url,
            "filename": filename,
            "decision_type": decision_type,
            "page_label": page_label,
            "date": date,
            "year": year,
        })

    return results


def download_and_extract(session: requests.Session, pdf_url: str) -> Optional[str]:
    """Download a PDF and extract text using PyMuPDF."""
    try:
        response = session.get(pdf_url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed to download {pdf_url}: {e}", file=sys.stderr)
        return None

    content = response.content
    if not content or len(content) < 100:
        return None

    if not (content[:4] == b'%PDF' or
            response.headers.get("Content-Type", "").startswith("application/pdf")):
        print(f"  Not a PDF: {pdf_url}", file=sys.stderr)
        return None

    url_hash = hashlib.md5(pdf_url.encode()).hexdigest()[:12]
    text = extract_pdf_markdown(
        source="ME/AZZK",
        source_id=f"azzk-{url_hash}",
        pdf_bytes=content,
        table="doctrine",
    )

    return text if text and len(text) >= 50 else None


def normalize(raw: dict) -> dict:
    """Normalize raw document data to standard schema."""
    url_hash = hashlib.md5(raw.get("pdf_url", "").encode()).hexdigest()[:10]
    _id = f"ME-AZZK-{url_hash}"

    return {
        "_id": _id,
        "_source": "ME/AZZK",
        "_type": "doctrine",
        "_fetched_at": datetime.utcnow().isoformat() + "Z",
        "title": raw.get("title") or f"AZZK Decision {url_hash}",
        "text": raw.get("text", ""),
        "date": raw.get("date"),
        "url": raw.get("pdf_url", ""),
        "category": raw.get("decision_type", ""),
        "decision_type": raw.get("decision_type", ""),
        "language": "sr",
    }


def fetch_all(session: requests.Session, max_docs: int = 1000) -> Iterator[dict]:
    """Fetch all decisions with full text."""
    count = 0
    all_entries = []

    for page_info in DECISION_PAGES:
        page_url = f"{BASE_URL}{page_info['url']}"
        print(f"\nFetching {page_info['label']} from {page_url}...", file=sys.stderr)
        entries = parse_pdf_links(session, page_url, page_info["type"], page_info["label"])
        print(f"  Found {len(entries)} PDF links", file=sys.stderr)
        all_entries.extend(entries)
        time.sleep(REQUEST_DELAY)

    # Deduplicate by URL
    seen = set()
    unique_entries = []
    for entry in all_entries:
        if entry["pdf_url"] not in seen:
            seen.add(entry["pdf_url"])
            unique_entries.append(entry)

    print(f"\nTotal unique PDFs: {len(unique_entries)}", file=sys.stderr)

    for entry in unique_entries:
        if count >= max_docs:
            break

        print(f"  [{count+1}] Downloading: {entry['title'][:60]}...", file=sys.stderr)
        text = download_and_extract(session, entry["pdf_url"])
        time.sleep(REQUEST_DELAY)

        if not text:
            print(f"    Skipped (no text extracted)", file=sys.stderr)
            continue

        entry["text"] = text
        record = normalize(entry)
        count += 1
        yield record

    print(f"\nDone. Yielded {count} records with full text.", file=sys.stderr)


def bootstrap_sample(max_records: int = 15):
    """Fetch sample records and save to sample/ directory."""
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    session = get_session()
    count = 0

    for record in fetch_all(session, max_docs=max_records):
        count += 1
        filename = f"{record['_id']}.json"
        filepath = sample_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"  Saved: {filename} ({len(record.get('text', ''))} chars)", file=sys.stderr)

    print(f"\nSample complete: {count} records saved to {sample_dir}", file=sys.stderr)
    return count


def bootstrap_fast():
    """Alias for bootstrap_sample used by VPS runner."""
    return bootstrap_sample(max_records=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ME/AZZK Competition Decisions Fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch sample records only")
    parser.add_argument("--max", type=int, default=15,
                        help="Maximum records to fetch")
    args = parser.parse_args()

    if args.command == "bootstrap-fast":
        bootstrap_fast()
    elif args.command == "bootstrap" and args.sample:
        bootstrap_sample(max_records=args.max)
    elif args.command == "bootstrap":
        bootstrap_sample(max_records=args.max)
