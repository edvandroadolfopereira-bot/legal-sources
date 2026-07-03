#!/usr/bin/env python3
"""
VA/CodexCanonumOrientalium - Code of Canons of the Eastern Churches (1990) Fetcher

Fetches the Codex Canonum Ecclesiarum Orientalium (CCEO) from vatican.va.
Promulgated by Pope John Paul II on 1990-10-18, in force since 1991-01-01.
1546 canons in 30 titles — the common code of canon law for the 23 Eastern
Catholic Churches. Companion to the 1983 Latin Code (VA/CodexIurisCanonici).

Official Latin text only (the Vatican site does not host a free English
translation of the CCEO). The text is split across three static HTML pages.

Data source: https://www.vatican.va/content/john-paul-ii/la/apost_constitutions/documents/
Method: Static HTML scraping (3 Latin pages, canon-by-canon parse)
License: Public Domain (Holy See)
Rate limit: ~2 seconds between requests
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import requests

SOURCE_ID = "VA/CodexCanonumOrientalium"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"
BASE_URL = "https://www.vatican.va"
DOC_BASE = ("/content/john-paul-ii/la/apost_constitutions/documents/"
            "hf_jp-ii_apc_19901018_codex-can-eccl-orient-{n}.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,*/*",
}

DELAY = 2  # seconds between requests
PROMULGATION_DATE = "1990-10-18"  # Apostolic Constitution Sacri Canones

# The CCEO is published across three content pages, by canon range.
DOC_PAGES = [1, 2, 3]


def strip_html(html_text: str) -> str:
    """Remove HTML tags and clean text."""
    if not html_text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html_text)
    text = re.sub(r"</?p[^>]*>", "\n", text)
    text = re.sub(r"</?blockquote[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch an HTML page with retries."""
    for attempt in range(3):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                print(f"  404: {url}")
                return None
            print(f"  HTTP {resp.status_code}, retrying...")
            time.sleep(DELAY * 2)
        except requests.RequestException as e:
            print(f"  Error (attempt {attempt + 1}): {e}")
            time.sleep(DELAY)
    return None


# Canon markers look like: <b>Can. 64</b> - text
# Some carry nested markup before </b>, e.g. <b>Can. 66<i><sup>n</sup></i> </b>
CANON_PATTERN = re.compile(r'<(?:b|strong)>\s*Can\.\s*(\d+)', re.IGNORECASE)


def parse_canons_from_html(html: str) -> List[Tuple[int, str]]:
    """Parse individual canons from a CCEO content page.

    Returns list of (canon_number, canon_text) tuples. The text for a canon
    runs from the end of its closing bold tag to the start of the next canon
    marker.
    """
    canons = []
    matches = list(CANON_PATTERN.finditer(html))
    if not matches:
        return canons

    for i, match in enumerate(matches):
        canon_num = int(match.group(1))
        # Skip past the closing </b>/</strong> so the leading bold marker is
        # not included in the body text.
        after = html[match.end():]
        close = re.search(r'</(?:b|strong)>', after, re.IGNORECASE)
        start = match.end() + (close.end() if close else 0)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)

        text = strip_html(html[start:end])
        # Clean leading dash/separator that follows the canon marker.
        text = re.sub(r'^[\s—–\-–—:]+', '', text).strip()

        if text:
            canons.append((canon_num, text))

    return canons


def normalize(canon_num: int, latin_text: str, page_no: int) -> dict:
    """Normalize a canon into a standard record."""
    url = f"{BASE_URL}{DOC_BASE.format(n=page_no)}"
    return {
        "_id": f"VA-CCEO-Can-{canon_num}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"Canon {canon_num} (CCEO)",
        "text": latin_text,
        "canon_number": canon_num,
        "code": "Codex Canonum Ecclesiarum Orientalium",
        "date": PROMULGATION_DATE,
        "url": url,
        "language": "la",
    }


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    """Fetch all canons from the CCEO. Yields normalized records."""
    session = requests.Session()
    seen: Dict[int, str] = {}
    total = 0

    for page_no in DOC_PAGES:
        url = f"{BASE_URL}{DOC_BASE.format(n=page_no)}"
        print(f"  Fetching CCEO page {page_no}...")
        html = fetch_page(url, session)
        if not html:
            print(f"  ERROR: Could not fetch {url}")
            continue

        canons = parse_canons_from_html(html)
        print(f"  Parsed {len(canons)} canon markers from page {page_no}")

        for canon_num, latin_text in canons:
            # Keep the longest text for any duplicate canon marker.
            if canon_num in seen and len(seen[canon_num]) >= len(latin_text):
                continue
            seen[canon_num] = latin_text
            yield normalize(canon_num, latin_text, page_no)
            total += 1

            if sample and total >= 15:
                print(f"  Sample limit reached ({total} records)")
                return

        time.sleep(DELAY)

    print(f"  Total canons fetched: {total}")


def cmd_test(session: requests.Session) -> bool:
    """Test connectivity to vatican.va and parse the first CCEO page."""
    url = f"{BASE_URL}{DOC_BASE.format(n=1)}"
    html = fetch_page(url, session)
    if not html:
        print("FAIL: Could not fetch CCEO page 1")
        return False
    canons = parse_canons_from_html(html)
    if len(canons) < 200:
        print(f"FAIL: Expected 200+ canons on page 1, got {len(canons)}")
        return False
    print(f"OK: page 1 has {len(canons)} canon markers")
    if canons[0][0] == 1:
        print(f"OK: Canon 1 starts with: {canons[0][1][:80]}...")
    return True


def main():
    parser = argparse.ArgumentParser(description="VA/CodexCanonumOrientalium fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch only sample data (~15 records)")
    parser.add_argument("--full", action="store_true",
                        help="Full bootstrap (all canons)")
    args = parser.parse_args()

    if args.command == "test":
        session = requests.Session()
        ok = cmd_test(session)
        sys.exit(0 if ok else 1)

    # bootstrap / bootstrap-fast
    is_sample = args.sample or (not args.full and args.command == "bootstrap")

    if is_sample:
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for record in fetch_all(sample=True):
            fname = SAMPLE_DIR / f"{record['_id']}.json"
            fname.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            count += 1
        print(f"\nSample bootstrap complete: {count} records")
        print(f"Samples saved to {SAMPLE_DIR}/")
    else:
        # Full run: stream to data/records.jsonl so the ingest host persists
        # every record (not just the sample/ files).
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "records.jsonl"
        count = 0
        with out.open("w", encoding="utf-8") as f:
            for record in fetch_all(sample=False):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        print(f"\nFull bootstrap complete: {count} records")
        print(f"Records written to {out}")


if __name__ == "__main__":
    main()
