#!/usr/bin/env python3
"""
INTL/Legislationline — OSCE/ODIHR Legal Opinions & Comments Fetcher

NOTE (rewrite, June 2026): The legacy legislationline.org Drupal JSON:API was
decommissioned. The whole legislationline.org domain now 302-redirects to
https://odihr.osce.org/odihr/legal-opinions-and-comments (Drupal 11, no JSON:API).
The migrated, publicly available corpus is ODIHR's legal opinions and comments —
expert legal reviews of draft/enacted laws across OSCE participating states. These
are advisory/commentary documents, so they are classified as `doctrine` (the old
~14K national-legislation corpus — constitutions, criminal codes — was not carried
over to the new site). See issue #973.

Each document is an HTML node page at https://odihr.osce.org/odihr/{node_id} with an
introductory summary (HTML body) and a full-text PDF (the opinion itself). We fetch
the listing, then for each node download and extract the PDF full text.

Data source: https://odihr.osce.org/odihr/legal-opinions-and-comments
Method: HTML listing scrape + per-node PDF full-text extraction
License: Custom terms (free access, attribution required — OSCE/ODIHR)

Usage:
  python bootstrap.py bootstrap --sample    # Fetch sample records
  python bootstrap.py bootstrap             # Full bootstrap -> data/records.jsonl
  python bootstrap.py bootstrap-fast        # VPS pipeline alias (same as bootstrap)
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
from urllib.parse import urljoin

import requests

# Make common helpers importable when run from the source dir or the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from common.pdf_extract import _fetch_pdf_bytes, _extract  # noqa: E402

BASE_URL = "https://odihr.osce.org"
LISTING_URL = f"{BASE_URL}/odihr/legal-opinions-and-comments"
SOURCE_ID = "INTL/Legislationline"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

RATE_LIMIT_DELAY = 1.0

# English country-name prefix (as used in ODIHR opinion titles) -> ISO 3166-1 alpha-2.
COUNTRY_NAME_MAP = {
    "Albania": "AL", "Andorra": "AD", "Armenia": "AM", "Austria": "AT",
    "Azerbaijan": "AZ", "Belarus": "BY", "Belgium": "BE",
    "Bosnia and Herzegovina": "BA", "Bulgaria": "BG", "Canada": "CA",
    "China": "CN", "Croatia": "HR", "Cyprus": "CY", "Czech Republic": "CZ",
    "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE", "Finland": "FI",
    "France": "FR", "Georgia": "GE", "Germany": "DE", "Greece": "GR",
    "Holy See": "VA", "Hungary": "HU", "Iceland": "IS", "Ireland": "IE",
    "Italy": "IT", "Kazakhstan": "KZ", "Kosovo": "XK", "Kyrgyzstan": "KG",
    "Latvia": "LV", "Liechtenstein": "LI", "Lithuania": "LT",
    "Luxembourg": "LU", "Malta": "MT", "Moldova": "MD", "Monaco": "MC",
    "Mongolia": "MN", "Montenegro": "ME", "Netherlands": "NL",
    "North Macedonia": "MK", "Norway": "NO", "Poland": "PL", "Portugal": "PT",
    "Romania": "RO", "Russia": "RU", "Russian Federation": "RU",
    "San Marino": "SM", "Serbia": "RS", "Slovakia": "SK", "Slovenia": "SI",
    "Spain": "ES", "Sweden": "SE", "Switzerland": "CH", "Tajikistan": "TJ",
    "Turkey": "TR", "Türkiye": "TR", "Turkmenistan": "TM", "Ukraine": "UA",
    "United Kingdom": "GB", "United States": "US",
    "United States of America": "US", "Uzbekistan": "UZ",
}


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities into clean text."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_country(title: str) -> Optional[str]:
    """Extract ISO country code from a 'Country: ...' title prefix."""
    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if prefix in COUNTRY_NAME_MAP:
            return COUNTRY_NAME_MAP[prefix]
    return None


def fetch_listing(session: requests.Session) -> list:
    """Fetch the legal-opinions-and-comments listing; return [(node_url, title)]."""
    resp = session.get(LISTING_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    page = resp.text

    results = []
    seen = set()
    # Each document is a <a class="teaser teaser--two-cols" href="/odihr/NNN" ...>
    # followed (within the block) by an <h2 class="teaser__title">Title</h2>.
    for block in re.split(r'<a\s+class="teaser teaser--two-cols"', page)[1:]:
        hm = re.search(r'href="(/odihr/\d+)"', block)
        if not hm:
            continue
        path = hm.group(1)
        if path in seen:
            continue
        tm = re.search(r'teaser__title[^>]*>(.*?)</', block, re.S)
        title = strip_html(tm.group(1)) if tm else ""
        seen.add(path)
        results.append((urljoin(BASE_URL, path), title))
    return results


def fetch_node(session: requests.Session, node_url: str) -> Optional[dict]:
    """Fetch a single document node page and parse metadata + PDF link."""
    resp = session.get(node_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    page = resp.text

    # Title (og:title is the cleanest source).
    tm = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page)
    title = html.unescape(tm.group(1)).strip() if tm else ""

    # Publication date: first <time datetime="..."> in the page is the doc date.
    dm = re.search(r'datetime="(\d{4}-\d{2}-\d{2})', page)
    date = dm.group(1) if dm else None

    # Introductory summary (HTML body section).
    sm = re.search(
        r'<div class="body body-section is-text text--default"[^>]*>(.*?)</div>\s*</div>',
        page,
        re.S,
    )
    summary = strip_html(sm.group(1)) if sm else ""

    # PDF full-text link (prefer English; take first otherwise).
    pdf_links = re.findall(r'href="(/sites/default/files/[^"]*\.pdf)"', page)
    pdf_url = urljoin(BASE_URL, pdf_links[0]) if pdf_links else None

    return {
        "node_url": node_url,
        "title": title,
        "date": date,
        "summary": summary,
        "pdf_url": pdf_url,
    }


def normalize(raw: dict) -> Optional[dict]:
    """Fetch full text for a listing item and build a normalized record."""
    session = raw.get("_session") or requests.Session()
    node = fetch_node(session, raw["node_url"])
    if not node:
        return None

    title = node["title"] or raw.get("title") or ""

    # Full text from the PDF; fall back to the HTML summary if no/empty PDF.
    text = ""
    if node["pdf_url"]:
        pdf_bytes = _fetch_pdf_bytes(node["pdf_url"])
        if pdf_bytes:
            extracted = _extract(pdf_bytes)
            if extracted:
                text = extracted.strip()
    if len(text) < 200 and node["summary"]:
        text = node["summary"] if len(node["summary"]) > len(text) else text

    if not text or len(text) < 100:
        return None

    node_id = re.search(r"/odihr/(\d+)", raw["node_url"])
    node_id = node_id.group(1) if node_id else raw["node_url"].rstrip("/").split("/")[-1]

    return {
        "_id": f"odihr-opinion-{node_id}",
        "_source": SOURCE_ID,
        "_type": "doctrine",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": node["date"],
        "url": raw["node_url"],
        "country": parse_country(title),
        "summary": node["summary"] or None,
        "pdf_url": node["pdf_url"],
        "publisher": "OSCE Office for Democratic Institutions and Human Rights (ODIHR)",
        "language": "en",
    }


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    """Yield normalized ODIHR legal-opinion records with full text."""
    session = requests.Session()
    listing = fetch_listing(session)
    print(
        f"Found {len(listing)} documents in ODIHR legal-opinions listing "
        f"({'sample' if sample else 'full'} mode)",
        file=sys.stderr,
    )

    target = 12 if sample else len(listing)
    count = 0
    for node_url, title in listing:
        if count >= target:
            break
        try:
            record = normalize({"node_url": node_url, "title": title, "_session": session})
        except requests.RequestException as e:
            print(f"  Error on {node_url}: {e}", file=sys.stderr)
            continue
        if record:
            count += 1
            yield record
            if count % 25 == 0:
                print(f"  {count} records with full text...", file=sys.stderr)
        time.sleep(RATE_LIMIT_DELAY)

    print(f"Total: {count} records with full text", file=sys.stderr)


def fetch_updates(since: str) -> Generator[dict, None, None]:
    """Yield records published on/after `since` (ISO date)."""
    for record in fetch_all(sample=False):
        if not record.get("date") or record["date"] >= since:
            yield record


def save_sample(records: list, sample_dir: Path) -> None:
    """Write sample records individually and as a combined file."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    for i, record in enumerate(records):
        with open(sample_dir / f"record_{i:04d}.json", "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    with open(sample_dir / "all_samples.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    if records:
        lens = [len(r["text"]) for r in records]
        countries = sorted({r["country"] for r in records if r.get("country")})
        print(
            f"Text lengths: min={min(lens)}, max={max(lens)}, avg={sum(lens)//len(lens)}",
            file=sys.stderr,
        )
        print(f"Countries: {len(countries)} — {countries}", file=sys.stderr)


def test_connectivity() -> bool:
    """Verify the listing loads and a document yields full text."""
    session = requests.Session()
    try:
        listing = fetch_listing(session)
        print(f"Listing OK: {len(listing)} documents found")
        if not listing:
            return False
        node = fetch_node(session, listing[0][0])
        print(f"First doc: {listing[0][1][:80]}")
        print(f"  PDF: {node['pdf_url']}")
        if node["pdf_url"]:
            b = _fetch_pdf_bytes(node["pdf_url"])
            txt = _extract(b) if b else None
            print(f"  PDF full text: {len(txt) if txt else 0} chars")
        return True
    except Exception as e:
        print(f"Connectivity FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="INTL/Legislationline (OSCE/ODIHR) bootstrap")
    parser.add_argument(
        "command", choices=["bootstrap", "bootstrap-fast", "test"], help="Command to run"
    )
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Full bootstrap (all records)")
    args = parser.parse_args()

    if args.command == "test":
        sys.exit(0 if test_connectivity() else 1)

    script_dir = Path(__file__).parent
    sample_mode = args.sample or not args.full

    if sample_mode and args.sample:
        records = list(fetch_all(sample=True))
        save_sample(records, script_dir / "sample")
        print(f"\nSaved {len(records)} sample records", file=sys.stderr)
        if not records:
            sys.exit(1)
        return

    # Full bootstrap: stream to data/records.jsonl for the VPS ingest pipeline.
    data_dir = script_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = data_dir / "records.jsonl"
    count = 0
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in fetch_all(sample=False):
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    print(f"Full bootstrap complete: {count} records -> {jsonl_path}", file=sys.stderr)
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
