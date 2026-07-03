#!/usr/bin/env python3
"""
US/USCode -- United States Code (Codified Federal Statutes)

Fetches all 54 titles of the United States Code from GovInfo.
Uses public content URLs — NO API KEY REQUIRED.

Each record is one USC section with full statutory text.

Usage:
    python bootstrap.py bootstrap --sample   # Fetch sample records
    python bootstrap.py bootstrap --full     # Fetch all titles
    python bootstrap.py updates --since YYYY-MM-DD  # Incremental updates
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

# Configuration
SOURCE_ID = "US/USCode"
GOVINFO_BASE = "https://www.govinfo.gov"
USER_AGENT = "LegalDataHunter/1.0 (Open Data Research; contact@legaldatahunter.com)"
REQUEST_DELAY = 1.0  # seconds between requests

# Most recent complete edition year
CURRENT_YEAR = 2024

# All USC title numbers (no title 53)
ALL_TITLES = list(range(1, 55))  # 1-54

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
SAMPLE_DIR = SCRIPT_DIR / "sample"


class USCHTMLParser(HTMLParser):
    """Parse GovInfo USC HTML to extract sections with full text."""

    def __init__(self):
        super().__init__()
        self.sections = []
        self._current_section = None
        self._in_statute = False
        self._in_notes = False
        self._in_source_credit = False
        self._in_heading = False
        self._text_parts = []
        self._heading_text = []
        self._current_doc_id = None
        self._current_item_path = None
        self._current_expcite = None
        self._skip_depth = 0

    def handle_comment(self, data):
        data = data.strip()
        if data.startswith("documentid:"):
            self._finalize_section()
            # doc_id comment format: "documentid:1_7  usckey:... currentthrough:..."
            # Extract only the first token (the actual ID)
            raw_id = data.split(":", 1)[1].strip()
            self._current_doc_id = raw_id.split()[0] if raw_id else raw_id
            self._current_section = {
                "doc_id": self._current_doc_id,
                "text_parts": [],
                "heading": "",
                "item_path": "",
                "expcite": "",
                "source_credit": "",
            }
        elif data.startswith("itempath:"):
            if self._current_section:
                self._current_section["item_path"] = data.split(":", 1)[1].strip()
        elif data.startswith("expcite:"):
            if self._current_section:
                self._current_section["expcite"] = data.split(":", 1)[1].strip()
        elif data == "field-start:statute":
            self._in_statute = True
            self._text_parts = []
        elif data == "field-end:statute":
            if self._current_section and self._text_parts:
                self._current_section["text_parts"].extend(self._text_parts)
            self._in_statute = False
            self._text_parts = []
        elif data == "field-start:sourcecredit":
            self._in_source_credit = True
            self._text_parts = []
        elif data == "field-end:sourcecredit":
            if self._current_section and self._text_parts:
                self._current_section["source_credit"] = " ".join(
                    t.strip() for t in self._text_parts if t.strip()
                )
            self._in_source_credit = False
            self._text_parts = []
        elif data == "field-start:notes":
            self._in_notes = True
        elif data == "field-end:notes":
            self._in_notes = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if tag == "h3" and "section-head" in cls:
            self._in_heading = True
            self._heading_text = []

    def handle_endtag(self, tag):
        if tag == "h3" and self._in_heading:
            self._in_heading = False
            if self._current_section:
                self._current_section["heading"] = " ".join(
                    t.strip() for t in self._heading_text if t.strip()
                )

    def handle_data(self, data):
        if self._in_heading:
            self._heading_text.append(data)
        elif self._in_statute or self._in_source_credit:
            self._text_parts.append(data)

    def handle_entityref(self, name):
        char = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "sect": "§"}.get(
            name, f"&{name};"
        )
        if self._in_heading:
            self._heading_text.append(char)
        elif self._in_statute or self._in_source_credit:
            self._text_parts.append(char)

    def handle_charref(self, name):
        try:
            if name.startswith("x"):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
        except (ValueError, OverflowError):
            char = f"&#{name};"
        if self._in_heading:
            self._heading_text.append(char)
        elif self._in_statute or self._in_source_credit:
            self._text_parts.append(char)

    def _finalize_section(self):
        if self._current_section and self._current_section.get("text_parts"):
            raw_text = " ".join(
                t.strip()
                for t in self._current_section["text_parts"]
                if t.strip()
            )
            # Clean up whitespace
            raw_text = re.sub(r"\s+", " ", raw_text).strip()
            if len(raw_text) >= 50:
                self._current_section["full_text"] = raw_text
                self.sections.append(self._current_section)
        self._current_section = None

    def close(self):
        self._finalize_section()
        super().close()


class USCodeClient:
    """Client for fetching US Code from GovInfo content URLs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html, application/xml, application/json",
        })

    def _get(self, url: str, retries: int = 3, timeout: int = 120) -> Optional[requests.Response]:
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    print(f"  Timeout, retrying ({attempt + 1}/{retries})...")
                    time.sleep(2)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                if attempt < retries - 1:
                    print(f"  Error: {e}, retrying ({attempt + 1}/{retries})...")
                    time.sleep(2)
                    continue
                return None
        return None

    def get_title_html(self, title_num: int, year: int = CURRENT_YEAR) -> Optional[str]:
        """Fetch the full HTML for a USC title."""
        pkg = f"USCODE-{year}-title{title_num}"
        url = f"{GOVINFO_BASE}/content/pkg/{pkg}/html/{pkg}.htm"
        resp = self._get(url, timeout=300)
        if resp:
            return resp.text
        return None

    def get_content_detail(self, title_num: int, year: int = CURRENT_YEAR) -> Optional[Dict]:
        """Get metadata for a USC title package."""
        pkg = f"USCODE-{year}-title{title_num}"
        url = f"{GOVINFO_BASE}/wssearch/getContentDetail?packageId={pkg}"
        resp = self._get(url)
        if resp:
            try:
                return resp.json()
            except json.JSONDecodeError:
                return None
        return None

    def get_sitemap(self, year: int = CURRENT_YEAR) -> List[str]:
        """Get list of available USC title package IDs from sitemap."""
        url = f"{GOVINFO_BASE}/sitemap/USCODE_{year}_sitemap.xml"
        resp = self._get(url)
        if not resp:
            return []
        try:
            root = ET.fromstring(resp.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            urls = []
            for loc in root.findall(".//sm:loc", ns):
                if loc.text:
                    urls.append(loc.text.strip())
            return urls
        except ET.ParseError:
            return []


def parse_title_html(html_content: str, title_num: int, year: int = CURRENT_YEAR) -> List[Dict]:
    """Parse a USC title HTML file into individual section records."""
    parser = USCHTMLParser()
    parser.feed(html_content)
    parser.close()

    records = []
    for section in parser.sections:
        doc_id = section.get("doc_id", "")
        heading = section.get("heading", "")
        full_text = section.get("full_text", "")
        expcite = section.get("expcite", "")
        item_path = section.get("item_path", "")
        source_credit = section.get("source_credit", "")

        if not full_text:
            continue

        # Build title from heading and expcite
        title_str = heading if heading else f"Title {title_num}, {doc_id}"

        # Build the full text with source credit if available
        text_with_credit = full_text
        if source_credit:
            text_with_credit += f"\n\nSource: {source_credit}"

        # Parse a section number from doc_id (e.g., "1_7" -> section 7 of title 1)
        section_num = doc_id.split("_", 1)[1] if "_" in doc_id else doc_id

        record = normalize(
            doc_id=doc_id,
            title=title_str,
            text=text_with_credit,
            title_num=title_num,
            section_num=section_num,
            year=year,
            expcite=expcite,
            item_path=item_path,
        )
        records.append(record)

    return records


def normalize(
    doc_id: str,
    title: str,
    text: str,
    title_num: int,
    section_num: str,
    year: int,
    expcite: str = "",
    item_path: str = "",
) -> Dict:
    """Transform extracted data into normalized schema."""
    pkg = f"USCODE-{year}-title{title_num}"
    url = f"{GOVINFO_BASE}/content/pkg/{pkg}/html/{pkg}.htm"

    return {
        "_id": f"usc-{year}-t{title_num}-s{section_num}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": f"{year}-01-01",
        "url": url,
        "usc_title": title_num,
        "usc_section": section_num,
        "edition_year": year,
        "citation_path": expcite,
        "item_path": item_path,
    }


def fetch_title_sections(client: USCodeClient, title_num: int, year: int = CURRENT_YEAR) -> List[Dict]:
    """Fetch and parse all sections from a single USC title."""
    print(f"  Fetching Title {title_num} (year {year})...")
    html_content = client.get_title_html(title_num, year)
    time.sleep(REQUEST_DELAY)

    if not html_content:
        print(f"    Title {title_num}: no content returned")
        return []

    size_mb = len(html_content) / (1024 * 1024)
    print(f"    Title {title_num}: {size_mb:.1f} MB HTML")

    # Skip extremely large titles in sample mode (>50MB)
    if size_mb > 200:
        print(f"    Title {title_num}: skipping (too large: {size_mb:.0f} MB)")
        return []

    records = parse_title_html(html_content, title_num, year)
    print(f"    Title {title_num}: {len(records)} sections extracted")
    return records


def fetch_sample(client: USCodeClient) -> List[Dict]:
    """Fetch sample sections from a few representative titles."""
    print("Fetching US Code samples from GovInfo (no API key required)...")
    all_records = []

    # Pick small-to-medium titles for sampling
    # Title 1 (General Provisions - small), Title 4 (Flag/Seal - small),
    # Title 11 (Bankruptcy - medium), Title 13 (Census - small)
    sample_titles = [1, 4, 11, 13]

    for title_num in sample_titles:
        records = fetch_title_sections(client, title_num)
        if records:
            # Take up to 5 sections from each title for sampling
            all_records.extend(records[:5])
        if len(all_records) >= 15:
            break

    return all_records


def fetch_all(sample: bool = False) -> Generator[Dict, None, None]:
    """Fetch all USC sections. Standard interface for VPS bootstrap runner."""
    client = USCodeClient()

    if sample:
        for record in fetch_sample(client):
            yield record
    else:
        print("Starting full US Code fetch (all titles)...")
        for title_num in ALL_TITLES:
            try:
                records = fetch_title_sections(client, title_num)
                for record in records:
                    yield record
            except Exception as e:
                print(f"  Error on Title {title_num}: {e}")
            time.sleep(REQUEST_DELAY)


def save_samples(records: List[Dict]) -> None:
    """Save sample records to the sample directory."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    for i, record in enumerate(records):
        filepath = SAMPLE_DIR / f"record_{i:04d}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    all_samples = SAMPLE_DIR / "all_samples.json"
    with open(all_samples, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(records)} samples to {SAMPLE_DIR}")


def validate_samples(sample_dir: Path) -> bool:
    """Validate sample records meet requirements."""
    samples = list(sample_dir.glob("record_*.json"))

    if len(samples) < 10:
        print(f"FAIL: Only {len(samples)} samples, need at least 10")
        return False

    all_valid = True
    total_text_len = 0

    for sample_path in sorted(samples):
        with open(sample_path, "r", encoding="utf-8") as f:
            record = json.load(f)

        text = record.get("text", "")
        if not text:
            print(f"FAIL: {sample_path.name} has no text")
            all_valid = False
        elif len(text) < 50:
            print(f"WARN: {sample_path.name} has short text ({len(text)} chars)")

        total_text_len += len(text)

        for field in ["_id", "_source", "_type", "title"]:
            if not record.get(field):
                print(f"WARN: {sample_path.name} missing {field}")

        if text and re.search(r"<[a-z]+[^>]*>", text, re.IGNORECASE):
            print(f"WARN: {sample_path.name} may contain HTML tags")

    avg_len = total_text_len // len(samples) if samples else 0
    print(f"\nValidation summary:")
    print(f"  Samples: {len(samples)}")
    print(f"  Average text length: {avg_len:,} chars")
    print(f"  All valid: {all_valid}")

    return all_valid and len(samples) >= 10


def main():
    parser = argparse.ArgumentParser(description="US/USCode — United States Code fetcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Initial data fetch")
    bootstrap_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    bootstrap_parser.add_argument("--full", action="store_true", help="Fetch all titles")

    # VPS wrapper compatibility: bootstrap-fast == bootstrap --full
    fast_parser = subparsers.add_parser("bootstrap-fast", help="Full fetch (VPS wrapper alias)")
    fast_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    fast_parser.add_argument("--full", action="store_true", help="Fetch all titles")

    updates_parser = subparsers.add_parser("updates", help="Fetch updates")
    updates_parser.add_argument("--since", required=True, help="Date (YYYY-MM-DD)")
    updates_parser.add_argument("--full", action="store_true", help="Fetch all records")

    subparsers.add_parser("validate", help="Validate sample records")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        valid = validate_samples(SAMPLE_DIR)
        sys.exit(0 if valid else 1)

    if args.command in ("bootstrap", "bootstrap-fast"):
        # bootstrap-fast defaults to a full fetch when neither flag is given
        if args.command == "bootstrap-fast" and not args.sample:
            args.full = True
        if args.sample:
            print("Fetching US Code samples...")
            client = USCodeClient()
            records = fetch_sample(client)
            if records:
                save_samples(records)
                text_lengths = [len(r.get("text", "")) for r in records]
                avg_len = sum(text_lengths) / len(text_lengths)
                print(f"\nSummary:")
                print(f"  Records: {len(records)}")
                print(f"  Avg text length: {avg_len:,.0f} chars")
                print(f"  Min text length: {min(text_lengths):,} chars")
                print(f"  Max text length: {max(text_lengths):,} chars")
                print("\nValidating samples...")
                valid = validate_samples(SAMPLE_DIR)
                sys.exit(0 if len(records) >= 10 and valid else 1)
            else:
                print("No records fetched!", file=sys.stderr)
                sys.exit(1)

        elif args.full:
            print("Starting full US Code fetch...")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            jsonl_path = DATA_DIR / "records.jsonl"
            count = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in fetch_all(sample=False):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 100 == 0:
                        print(f"  Written {count} sections...")
            print(f"\nTotal: {count} sections written -> {jsonl_path}")
            sys.exit(0)
        else:
            print("Use --sample or --full")
            sys.exit(1)

    elif args.command == "updates":
        print(f"Checking for USC updates since {args.since}...")
        # The US Code is updated annually; check if a newer edition year exists
        print("Note: US Code editions are annual. Check GovInfo for newer edition years.")
        sys.exit(0)


if __name__ == "__main__":
    main()
