#!/usr/bin/env python3
"""
SO/OSAG — Somalia Office of the State Attorney General — Official Gazette

Fetches legislation, cabinet decisions, resolutions, and agreements from
the OSAG Official Bulletin (Faafinta Rasmiga Ah). ~280 individual documents
published from 2014-present, each as a downloadable PDF.

Strategy:
  - Paginate bulletins-contents listing (10 per page, ~28 pages)
  - For each entry: reference number, title, issuing org, date, PDF URL
  - Download PDF and extract text using pdfplumber
  - Classify by URL path (legislation, cabinet-decisions, agreements, etc.)

Source: https://osagsomalia.com/en/resources/bulletins-contents/
Rate limit: 1.5 req/sec

Usage:
  python bootstrap.py test-api
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, unquote

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip3 install beautifulsoup4")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip3 install pdfplumber")
    sys.exit(1)

SOURCE_ID = "SO/OSAG"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SO.OSAG")

BASE_URL = "https://osagsomalia.com"
LISTING_URL = f"{BASE_URL}/en/resources/bulletins-contents/"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
    "Accept-Language": "en,so",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

RATE_LIMIT = 1.5
_last_request = 0.0

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _throttle():
    global _last_request
    now = time.time()
    wait = RATE_LIMIT - (now - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def _get(url, **kwargs):
    _throttle()
    resp = SESSION.get(url, timeout=60, **kwargs)
    resp.raise_for_status()
    return resp


def parse_date(date_str):
    """Parse date like 'Apr 2026' or 'Dec 2023' to ISO format."""
    date_str = date_str.strip()
    match = re.match(r"(\w{3})\s+(\d{4})", date_str)
    if match:
        month_abbr = match.group(1).lower()
        year = match.group(2)
        month = MONTH_MAP.get(month_abbr)
        if month:
            return f"{year}-{month}-01"
    # Try full date patterns
    for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def classify_type(pdf_path):
    """Classify document type from PDF URL path."""
    path_lower = pdf_path.lower()
    if "/legislation/" in path_lower:
        return "legislation"
    elif "/cabinet-decisions/" in path_lower or "/xeer/" in path_lower:
        return "legislation"  # Cabinet decisions with legal force
    elif "/agreements/" in path_lower:
        return "legislation"
    elif "/resolutions/" in path_lower:
        return "legislation"
    elif "/budget/" in path_lower:
        return "legislation"
    return "legislation"


def slug_from_ref_and_title(ref, title):
    """Create a unique slug from reference number and title."""
    combined = f"{ref}_{title}" if ref else title
    slug = re.sub(r"[^\w\-]", "-", combined)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:120]


def extract_pdf_text(pdf_bytes):
    """Extract text from PDF bytes using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    texts.append(text.strip())
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(texts)
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def get_listing_page(page_num):
    """Fetch a listing page and extract document entries."""
    url = f"{LISTING_URL}?page={page_num}"
    logger.info(f"Fetching listing page {page_num}: {url}")
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    entries = []
    table = soup.find("table")
    if not table:
        return entries

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        ref = cells[0].get_text(strip=True)
        title = cells[1].get_text(strip=True)
        issuing_org = cells[2].get_text(strip=True)
        date_str = cells[3].get_text(strip=True)

        # Find PDF link
        pdf_link = row.find("a", href=re.compile(r"\.pdf$", re.I))
        if not pdf_link:
            continue

        pdf_url = urljoin(BASE_URL, pdf_link["href"])

        entries.append({
            "ref": ref,
            "title": title,
            "issuing_org": issuing_org,
            "date_str": date_str,
            "pdf_url": pdf_url,
        })

    return entries


def fetch_all(sample=False):
    """Fetch all OSAG gazette documents."""
    all_entries = []
    max_pages = 30 if not sample else 3

    for page_num in range(1, max_pages + 1):
        entries = get_listing_page(page_num)
        if not entries:
            logger.info(f"No entries on page {page_num}, stopping pagination")
            break
        all_entries.extend(entries)
        logger.info(f"Page {page_num}: {len(entries)} entries (total: {len(all_entries)})")

    logger.info(f"Total entries found: {len(all_entries)}")

    seen_urls = set()
    count = 0
    for entry in all_entries:
        pdf_url = entry["pdf_url"]
        if pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        try:
            logger.info(f"Downloading: {entry['title'][:60]}")
            resp = _get(pdf_url)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {pdf_url}")
                continue

            text = extract_pdf_text(resp.content)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text from {pdf_url}: {len(text)} chars")
                continue

            date = parse_date(entry["date_str"])
            doc_type = classify_type(pdf_url)
            doc_id = slug_from_ref_and_title(entry["ref"], entry["title"])

            doc = {
                "_id": doc_id,
                "_source": SOURCE_ID,
                "_type": doc_type,
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": entry["title"],
                "text": text,
                "date": date,
                "url": pdf_url,
                "reference_number": entry["ref"],
                "issuing_organization": entry["issuing_org"],
                "language": "so",
            }

            yield doc
            count += 1
            logger.info(f"[{count}] {entry['ref']} {entry['title'][:50]} — {len(text)} chars")

            if sample and count >= 15:
                logger.info("Sample limit reached")
                return

        except Exception as e:
            logger.error(f"Error fetching {pdf_url}: {e}")
            continue

    logger.info(f"Total documents fetched: {count}")


def save_sample(records, output_dir):
    """Save sample records as JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        fname = re.sub(r"[^\w\-]", "_", rec["_id"])[:80] + ".json"
        path = output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved: {path.name}")


def test_api():
    """Quick connectivity test."""
    print(f"Testing {LISTING_URL} ...")
    resp = _get(LISTING_URL)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        print(f"Table rows: {len(rows)}")
        pdf_links = [a["href"] for a in table.find_all("a", href=re.compile(r"\.pdf$", re.I))]
        print(f"PDF links: {len(pdf_links)}")
        for link in pdf_links[:3]:
            print(f"  - {link.split('/')[-1]}")
    # Check pagination
    pagination = soup.find_all("a", href=re.compile(r"page="))
    if pagination:
        pages = set()
        for a in pagination:
            m = re.search(r"page=(\d+)", a["href"])
            if m:
                pages.add(int(m.group(1)))
        if pages:
            print(f"Pages: 1-{max(pages)}")
    print("API test passed." if table else "WARNING: No table found!")


def main():
    parser = argparse.ArgumentParser(description="SO/OSAG bootstrapper")
    parser.add_argument("command", choices=["test-api", "bootstrap"])
    parser.add_argument("--sample", action="store_true", help="Save sample records only (15 docs)")
    parser.add_argument("--full", action="store_true", help="Run full bootstrap (all pages)")
    args = parser.parse_args()

    if args.command == "test-api":
        test_api()
    elif args.command == "bootstrap":
        records = list(fetch_all(sample=args.sample))
        if records:
            save_sample(records, SAMPLE_DIR)
            print(f"\nBootstrap complete: {len(records)} records saved to {SAMPLE_DIR}")
            text_lens = [len(r.get("text", "")) for r in records]
            print(f"Text lengths: min={min(text_lens)}, max={max(text_lens)}, avg={sum(text_lens)//len(text_lens)}")
        else:
            print("ERROR: No records fetched!")
            sys.exit(1)


if __name__ == "__main__":
    main()
