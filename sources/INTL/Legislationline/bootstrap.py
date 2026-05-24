#!/usr/bin/env python3
"""
INTL/Legislationline — OSCE/ODIHR Legislation Database Fetcher

Fetches legislation from the OSCE Legislationline database via Drupal JSON:API.
~14,000 documents covering 57 OSCE participating states. Human rights, rule of law,
elections, governance legislation. English translations and original language texts.

Data source: https://legislationline.org/
Method: Drupal JSON:API (taxonomy_term/files endpoint)
License: Custom terms (free access, attribution required)

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap             # Full bootstrap
  python bootstrap.py test                  # Test connectivity
"""

import argparse
import json
import re
import sys
import time
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import quote

import requests

BASE_URL = "https://legislationline.org/jsonapi"
SAMPLE_DIR = Path(__file__).parent / "sample"
SOURCE_ID = "INTL/Legislationline"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "application/vnd.api+json",
}

RATE_LIMIT_DELAY = 1.0
PAGE_SIZE = 50

# Legislation-related file_type taxonomy term IDs
LEGISLATION_TYPE_TIDS = {46, 48, 49, 50, 52}  # Constitutions, Criminal codes, Legislation, Case law, Archives

# Country taxonomy TID -> ISO code mapping (OSCE participating states)
COUNTRY_TID_MAP = {
    1: "AL", 2: "AD", 3: "AM", 4: "AT", 5: "AZ",
    74: "SE", 75: "ES", 76: "SI", 77: "SK", 78: "RS",
    79: "SM", 80: "RU", 81: "RO", 82: "PT", 83: "PL",
    84: "NO", 85: "NL", 86: "MC", 87: "MD", 88: "MT",
    89: "LU", 90: "LT", 91: "LI", 92: "LV", 93: "KG",
    94: "KZ", 95: "IT", 96: "IE", 97: "IS", 98: "HU",
    99: "VA", 100: "GR", 101: "DE", 102: "GE", 103: "FR",
    104: "MK", 105: "FI", 106: "EE", 107: "DK", 108: "CZ",
    109: "CY", 110: "HR", 111: "CA", 112: "BG", 113: "BA",
    114: "BE", 115: "BY", 116: "CH", 117: "TJ", 118: "TR",
}

# Topic taxonomy TID -> name mapping
TOPIC_TID_MAP = {
    6: "Fair Trial", 7: "Freedom of Association",
    8: "Freedom of Peaceful Assembly", 9: "Freedom of Religion or Belief",
    10: "Gender Equality", 11: "Women's Participation",
    12: "Violence against Women", 13: "Hate Crimes",
    14: "Hate Crime Laws", 15: "Other Related Laws",
    16: "Judicial and Prosecution Systems", 126: "Citizenship",
    127: "National Minorities", 128: "Anti-Discrimination",
    129: "Administrative Justice", 130: "National Human Rights Institutions",
    131: "Lawmaking", 133: "Political Parties",
    135: "Counter-Terrorism", 136: "Elections",
    137: "Migration", 138: "Trafficking in Human Beings",
    139: "State of emergency", 140: "Referendum",
    10838: "Anti-Corruption", 10839: "Youth",
    25508: "Access to information",
}

# File type taxonomy TID -> name mapping
FILE_TYPE_TID_MAP = {
    21: "Opinions", 22: "Comments", 23: "Notes",
    46: "Constitutions", 48: "Criminal codes", 49: "Legislation",
    50: "Case law", 52: "Archives", 53: "Legal reviews",
    54: "Assessments", 55: "Guidelines", 56: "Treaty Standards",
    57: "Non-treaty standards", 58: "OSCE Commitments",
    59: "International Case-law", 60: "Others", 10840: "External link",
}


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def fetch_page(session: requests.Session, offset: int = 0) -> dict:
    """Fetch a page of documents from the JSON:API."""
    url = (
        f"{BASE_URL}/taxonomy_term/files"
        f"?page%5Blimit%5D={PAGE_SIZE}"
        f"&page%5Boffset%5D={offset}"
    )
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def resolve_country(item: dict) -> Optional[str]:
    """Extract country ISO code from relationship data."""
    country_rel = item.get("relationships", {}).get("field_country", {}).get("data")
    if country_rel and isinstance(country_rel, dict):
        tid = country_rel.get("meta", {}).get("drupal_internal__target_id")
        if tid:
            return COUNTRY_TID_MAP.get(tid)
    return None


def resolve_topics(item: dict) -> list:
    """Extract topic names from relationship data."""
    topics_rel = item.get("relationships", {}).get("field_document_topics", {}).get("data")
    if not topics_rel:
        return []
    if isinstance(topics_rel, dict):
        topics_rel = [topics_rel]
    result = []
    for t in topics_rel:
        tid = t.get("meta", {}).get("drupal_internal__target_id")
        if tid and tid in TOPIC_TID_MAP:
            result.append(TOPIC_TID_MAP[tid])
    return result


def resolve_file_type(item: dict) -> Optional[str]:
    """Extract file type name from relationship data."""
    ft_rel = item.get("relationships", {}).get("field_file_type", {}).get("data")
    if ft_rel and isinstance(ft_rel, dict):
        tid = ft_rel.get("meta", {}).get("drupal_internal__target_id")
        if tid:
            return FILE_TYPE_TID_MAP.get(tid)
    return None


def resolve_section(item: dict) -> Optional[str]:
    """Extract section name from relationship data."""
    sec_rel = item.get("relationships", {}).get("field_section", {}).get("data")
    if sec_rel and isinstance(sec_rel, dict):
        tid = sec_rel.get("meta", {}).get("drupal_internal__target_id")
        if tid:
            # Map section TIDs to document_type_main names
            section_map = {43: "Legislation", 44: "OSCE Documents", 45: "International Standards"}
            return section_map.get(tid)
    return None


def normalize(item: dict) -> Optional[dict]:
    """Transform a JSON:API taxonomy_term/files item into a normalized record."""
    attrs = item.get("attributes", {})
    tid = attrs.get("drupal_internal__tid")
    name = attrs.get("name", "")
    pub_date = attrs.get("field_publication_date")

    # Extract web content (full text)
    web_content = attrs.get("field_field_document_web_content")
    text = ""
    if web_content and isinstance(web_content, dict):
        raw_html = web_content.get("value", "")
        text = strip_html(raw_html)
    elif web_content and isinstance(web_content, str):
        text = strip_html(web_content)

    # Skip records without text
    if not text or len(text) < 50:
        return None

    country_code = resolve_country(item)
    topics = resolve_topics(item)
    file_type = resolve_file_type(item)
    section = resolve_section(item)

    return {
        "_id": f"legislationline-{tid}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": name,
        "text": text,
        "date": pub_date,
        "url": f"https://legislationline.org/taxonomy/term/{tid}",
        "country": country_code,
        "topics": topics,
        "document_type": file_type,
        "section": section,
        "language": attrs.get("langcode", "en"),
        "old_id": attrs.get("field_old_id"),
        "external_url": attrs.get("field_url"),
    }


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    """Fetch all legislation documents with full text from Legislationline."""
    session = requests.Session()
    offset = 0
    count = 0
    max_records = 15 if sample else 999999
    empty_pages = 0

    print(f"Fetching documents from Legislationline JSON:API ({'sample' if sample else 'full'} mode)...")

    while count < max_records:
        try:
            data = fetch_page(session, offset)
        except requests.RequestException as e:
            print(f"  Error at offset {offset}: {e}")
            break

        items = data.get("data", [])
        if not items:
            empty_pages += 1
            if empty_pages >= 3:
                print(f"  No more data after offset {offset}")
                break
            offset += PAGE_SIZE
            time.sleep(RATE_LIMIT_DELAY)
            continue

        empty_pages = 0
        for item in items:
            record = normalize(item)
            if record:
                count += 1
                yield record
                if count >= max_records:
                    break

        has_next = "next" in data.get("links", {})
        if not has_next:
            print(f"  Reached end of pagination at offset {offset}")
            break

        offset += PAGE_SIZE
        if offset % 500 == 0:
            print(f"  Processed offset {offset}, {count} records with text so far...")
        time.sleep(RATE_LIMIT_DELAY)

    print(f"Total: {count} records with full text")


def test_connectivity() -> bool:
    """Test that the JSON:API is accessible."""
    session = requests.Session()
    try:
        data = fetch_page(session, offset=500)
        items = data.get("data", [])
        print(f"Connectivity OK: got {len(items)} items from offset 500")
        wc = sum(1 for i in items if i.get("attributes", {}).get("field_field_document_web_content"))
        print(f"  {wc}/{len(items)} have web content (full text)")
        return True
    except Exception as e:
        print(f"Connectivity FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="INTL/Legislationline bootstrap")
    parser.add_argument("command", choices=["bootstrap", "test"], help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Full bootstrap (all records)")
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
            # Save each record individually
            safe_id = re.sub(r'[^\w-]', '_', record["_id"])
            out_path = SAMPLE_DIR / f"{safe_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        print(f"\nSaved {len(records)} records to {SAMPLE_DIR}/")

        # Validate
        if records:
            text_lens = [len(r["text"]) for r in records]
            print(f"Text lengths: min={min(text_lens)}, max={max(text_lens)}, avg={sum(text_lens)//len(text_lens)}")
            countries = set(r.get("country") for r in records if r.get("country"))
            print(f"Countries represented: {len(countries)} — {sorted(countries)[:10]}")
            with_date = sum(1 for r in records if r.get("date"))
            print(f"Records with date: {with_date}/{len(records)}")
        else:
            print("WARNING: No records fetched!")
            sys.exit(1)


if __name__ == "__main__":
    main()
