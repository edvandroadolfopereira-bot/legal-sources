#!/usr/bin/env python3
"""
LK/GovPrinter - Sri Lanka Department of Government Printing — Acts

Fetches Sri Lankan Acts of Parliament (1981-2026) from documents.gov.lk.
Each act is available as PDF in English, Sinhala, and Tamil.
This scraper fetches English PDFs and extracts full text.

Usage:
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap             # Full extraction
  python bootstrap.py test                  # Test connectivity
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

SOURCE_ID = "LK/GovPrinter"
SCRIPT_DIR = Path(__file__).parent
SAMPLE_DIR = SCRIPT_DIR / "sample"
DATA_DIR = SCRIPT_DIR / "data"

BASE_URL = "https://documents.gov.lk/view/act"
YEARS = list(range(2026, 1980, -1))  # 2026 down to 1981

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "LegalDataHunter/1.0 (research)"})


def fetch_page(url: str) -> str:
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  Failed to fetch {url}: {e}")
                return None


def fetch_pdf_bytes(url: str) -> bytes:
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=60)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  Failed to download PDF {url}: {e}")
                return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except Exception as e:
        print(f"  PDF extraction error: {e}")
        return ""


def parse_acts_page(year: int) -> list:
    """Parse a year's acts page and return list of act metadata."""
    url = f"{BASE_URL}/acts_{year}.html"
    html = fetch_page(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    acts = []

    # Find all table rows (skip header)
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Extract act number, date, description
        act_num_text = cells[0].get_text(strip=True)
        date_text = cells[1].get_text(strip=True)
        desc_text = cells[2].get_text(strip=True)

        if not act_num_text or not desc_text:
            continue

        # Find English PDF link
        pdf_link = None
        for a in row.find_all("a", href=True):
            href = a["href"]
            if "_E.pdf" in href or "_e.pdf" in href:
                pdf_link = href
                break

        if not pdf_link:
            # Try to find any PDF link
            for a in row.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower():
                    pdf_link = href
                    break

        if not pdf_link:
            continue

        # Construct full PDF URL
        if pdf_link.startswith("http"):
            pdf_url = pdf_link
        else:
            pdf_url = f"{BASE_URL}/{pdf_link}"

        # Parse date
        parsed_date = None
        for fmt in ["%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                parsed_date = datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

        # Extract act number
        act_num = re.sub(r"[^\d/]", "", act_num_text)

        acts.append({
            "act_number": act_num,
            "year": year,
            "date": parsed_date or date_text,
            "title": desc_text,
            "pdf_url": pdf_url,
        })

    return acts


def normalize(raw: dict, text: str) -> dict:
    act_id = f"LK-Act-{raw['act_number'].replace('/', '-')}"
    return {
        "_id": act_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"Act No. {raw['act_number']} — {raw['title']}",
        "text": text,
        "date": raw["date"],
        "url": raw["pdf_url"],
        "act_number": raw["act_number"],
        "year": raw["year"],
        "jurisdiction": "LK",
        "language": "en",
    }


def save_record(record: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{record['_id']}.json"
    filepath = output_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def cmd_test():
    print("Testing connectivity to documents.gov.lk...")
    html = fetch_page(f"{BASE_URL}/acts.html")
    if html and "2026" in html:
        print("OK — Acts index page accessible, years listed.")
        return True
    else:
        print("FAIL — Could not access acts index page.")
        return False


def cmd_bootstrap(sample=False):
    max_records = 15 if sample else 999999
    output_dir = SAMPLE_DIR if sample else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    total_saved = 0
    total_skipped = 0
    years_to_scan = YEARS[:5] if sample else YEARS  # Recent 5 years for sample

    print(f"{'Sample' if sample else 'Full'} bootstrap — scanning {len(years_to_scan)} years")

    for year in years_to_scan:
        if total_saved >= max_records:
            break

        print(f"\n--- Year {year} ---")
        acts = parse_acts_page(year)
        print(f"  Found {len(acts)} acts")

        for act in acts:
            if total_saved >= max_records:
                break

            print(f"  Downloading Act {act['act_number']}: {act['title'][:60]}...")
            pdf_bytes = fetch_pdf_bytes(act["pdf_url"])
            if not pdf_bytes:
                total_skipped += 1
                continue

            text = extract_text_from_pdf(pdf_bytes)
            if not text or len(text) < 50:
                print(f"    Insufficient text extracted ({len(text) if text else 0} chars)")
                total_skipped += 1
                continue

            record = normalize(act, text)
            save_record(record, output_dir)
            total_saved += 1
            print(f"    Saved ({len(text)} chars)")
            time.sleep(1)  # Rate limit

    print(f"\nDone: {total_saved} records saved, {total_skipped} skipped")
    return total_saved


def main():
    parser = argparse.ArgumentParser(description=f"{SOURCE_ID} bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap")
    boot.add_argument("--sample", action="store_true")

    sub.add_parser("test")

    args = parser.parse_args()

    if args.command == "test":
        sys.exit(0 if cmd_test() else 1)
    elif args.command == "bootstrap":
        count = cmd_bootstrap(sample=args.sample)
        sys.exit(0 if count > 0 else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
