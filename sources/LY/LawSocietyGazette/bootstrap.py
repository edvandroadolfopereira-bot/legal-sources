#!/usr/bin/env python3
"""
LY/LawSocietyGazette — Libya Law Society Legislation Archive

Fetches Libyan legislation from lawsociety.ly — 19,993 documents including
laws, decisions, decrees, regulations, circulars, and constitutional texts.
Full text in Arabic with structured metadata.

Data source: https://lawsociety.ly/legislation/
Method: HTML scraping (list pages + individual pages)
License: Open Government Data (official legislation)

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap --full     # Full bootstrap
  python bootstrap.py test                 # Test connectivity
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import unquote

import requests

BASE_URL = "https://lawsociety.ly"
LIST_URL = f"{BASE_URL}/legislation/"
SAMPLE_DIR = Path(__file__).parent / "sample"
SOURCE_ID = "LY/LawSocietyGazette"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept-Language": "ar,en;q=0.5",
}

RATE_LIMIT_DELAY = 1.5

# Map Arabic type labels to normalized types
TYPE_MAP = {
    "القوانين": "legislation",
    "القرارات": "legislation",
    "المراسيم": "legislation",
    "اللوائح": "legislation",
    "الدستور": "legislation",
    "المناشير": "legislation",
    "المشاريع": "legislation",
    "الاتفاقيات": "legislation",
    "الإعلانات": "legislation",
    "laws": "legislation",
    "decisions": "legislation",
    "decrees": "legislation",
    "regulations": "legislation",
    "constitutional": "legislation",
    "circulars": "legislation",
    "projects": "legislation",
    "conventions": "legislation",
    "announcements": "legislation",
}


def slug_from_url(url: str) -> str:
    """Extract the slug from a legislation URL."""
    path = url.rstrip("/").split("/legislation/")[-1]
    path = path.split("?")[0].split("#")[0].rstrip("/")
    # URL-decode for readability, then hash if too long
    decoded = unquote(path)
    if len(decoded) > 120:
        return hashlib.md5(path.encode()).hexdigest()[:16]
    return decoded


def extract_links_from_list_page(html: str) -> list[str]:
    """Extract individual legislation URLs from a list page."""
    # Match links to individual legislation pages (not filter/pagination links)
    pattern = r'href="(https://lawsociety\.ly/legislation/[^"?]+/)"'
    links = re.findall(pattern, html)
    # Deduplicate while preserving order, exclude pagination pages
    seen = set()
    unique = []
    for link in links:
        if "/page/" in link:
            continue
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def extract_text_from_page(html: str) -> dict:
    """Extract title, full text, date, and type from an individual legislation page."""
    result = {
        "title": "",
        "text": "",
        "date": None,
        "legislation_type": None,
        "status": None,
        "issuing_body": None,
    }

    # Extract title from <h1>
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1_match:
        result["title"] = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

    # Extract full text from <article>
    article_match = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL)
    if not article_match:
        return result

    article = article_match.group(1)

    # Extract all text content: paragraphs, list items, headings
    text_parts = []
    # Get paragraphs
    for p in re.finditer(r"<p[^>]*>(.*?)</p>", article, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", p.group(1)).strip()
        if clean:
            text_parts.append(clean)

    # Get list items
    for li in re.finditer(r"<li[^>]*>(.*?)</li>", article, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", li.group(1)).strip()
        if clean:
            text_parts.append(clean)

    # Get h2-h6 headings
    for h in re.finditer(r"<h[2-6][^>]*>(.*?)</h[2-6]>", article, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", h.group(1)).strip()
        if clean:
            text_parts.append(clean)

    result["text"] = "\n\n".join(text_parts)

    # Extract metadata from the first paragraph (contains type, date, etc.)
    first_p = text_parts[0] if text_parts else ""

    # Date extraction: look for dd-mm-yyyy pattern
    date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})", first_p)
    if date_match:
        day, month, year = date_match.groups()
        try:
            result["date"] = f"{year}-{month}-{day}"
        except ValueError:
            pass

    # Also try to find date in meta tags
    if not result["date"]:
        meta_date = re.search(r'datePublished["\s:]+(\d{4}-\d{2}-\d{2})', html)
        if meta_date:
            result["date"] = meta_date.group(1)

    # Type extraction
    for ar_type, en_type in TYPE_MAP.items():
        if ar_type in first_p:
            result["legislation_type"] = en_type
            break

    # Try meta description for type
    if not result["legislation_type"]:
        type_match = re.search(
            r'legislation_type=(\w+)', html
        )
        if type_match:
            t = type_match.group(1).lower()
            result["legislation_type"] = TYPE_MAP.get(t, "legislation")

    return result


def normalize(url: str, data: dict) -> Optional[dict]:
    """Create a normalized record."""
    if not data["text"] or len(data["text"]) < 50:
        return None

    slug = slug_from_url(url)
    doc_id = f"ly-lsg-{hashlib.md5(slug.encode()).hexdigest()[:12]}"

    # Detect court rulings from title keywords
    doc_type = data.get("legislation_type") or "legislation"
    title = data.get("title", "")
    court_keywords = ["المحكمة العليا", "المحكمة", "حكم", "طعن"]
    if any(kw in title for kw in court_keywords):
        doc_type = "case_law"

    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": doc_type,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": data["title"],
        "text": data["text"],
        "date": data["date"],
        "url": url,
        "country": "LY",
        "language": "ar",
        "legislation_type": data.get("legislation_type"),
        "status": data.get("status"),
    }


def get_list_page_urls(session: requests.Session, max_pages: int = 1000) -> Generator[str, None, None]:
    """Iterate through list pages and yield individual legislation URLs."""
    page = 1
    while page <= max_pages:
        if page == 1:
            url = LIST_URL
        else:
            url = f"{LIST_URL}page/{page}/"

        try:
            resp = session.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 404:
                print(f"  Page {page}: 404 — end of pagination")
                break
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Page {page}: ERROR {e}")
            break

        links = extract_links_from_list_page(resp.text)
        if not links:
            print(f"  Page {page}: no links found — end of pagination")
            break

        print(f"  Page {page}: {len(links)} links")
        for link in links:
            yield link

        page += 1
        time.sleep(RATE_LIMIT_DELAY)


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    """Fetch all legislation documents with full text."""
    session = requests.Session()
    max_records = 15 if sample else 999999
    max_pages = 2 if sample else 1000
    count = 0
    skipped = 0

    print(f"Fetching LY/LawSocietyGazette ({'sample' if sample else 'full'} mode)...")
    print(f"Collecting legislation URLs from list pages...")

    for doc_url in get_list_page_urls(session, max_pages=max_pages):
        if count >= max_records:
            break

        try:
            resp = session.get(doc_url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    ERROR fetching {doc_url}: {e}")
            skipped += 1
            continue

        data = extract_text_from_page(resp.text)
        record = normalize(doc_url, data)

        if not record:
            print(f"    SKIP (insufficient text): {data['title'][:60] if data['title'] else doc_url[-50:]}")
            skipped += 1
            continue

        count += 1
        print(f"    [{count}] {record['title'][:70]}  ({len(record['text'])} chars)")
        yield record

        time.sleep(RATE_LIMIT_DELAY)

    print(f"\nTotal: {count} records with full text, {skipped} skipped")


def test_connectivity() -> bool:
    """Test that the site is accessible and returns legislation data."""
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        links = extract_links_from_list_page(resp.text)
        print(f"Connectivity OK: status {resp.status_code}, {len(links)} links on first page")

        if links:
            resp2 = requests.get(links[0], headers=HEADERS, timeout=30)
            resp2.raise_for_status()
            data = extract_text_from_page(resp2.text)
            print(f"Sample page OK: title='{data['title'][:60]}', text={len(data['text'])} chars")
            return len(data["text"]) > 100

        return len(links) > 0
    except Exception as e:
        print(f"Connectivity FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="LY/LawSocietyGazette bootstrap")
    parser.add_argument("command", choices=["bootstrap", "test"], help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Full bootstrap")
    args = parser.parse_args()

    if args.command == "test":
        ok = test_connectivity()
        sys.exit(0 if ok else 1)

    if args.command == "bootstrap":
        sample_mode = args.sample or not args.full
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

        records = []
        for record in fetch_all(sample=sample_mode):
            records.append(record)
            safe_id = re.sub(r"[^\w-]", "_", record["_id"])
            out_path = SAMPLE_DIR / f"{safe_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        print(f"\nSaved {len(records)} records to {SAMPLE_DIR}/")

        if records:
            text_lens = [len(r["text"]) for r in records]
            print(f"Text lengths: min={min(text_lens)}, max={max(text_lens)}, avg={sum(text_lens)//len(text_lens)}")
        else:
            print("WARNING: No records fetched!")
            sys.exit(1)


if __name__ == "__main__":
    main()
