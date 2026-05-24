#!/usr/bin/env python3
"""
NI/SajurinGacetas — Nicaragua Official Gazette Archive

Fetches La Gaceta (Diario Oficial de Nicaragua) issues from the Enrique Bolaños
Foundation digital library. ~20,211 gazette issues from 1940s-2015+.

Strategy:
  - Paginate the gazette collection listing pages (15 results/page)
  - For each gazette issue, extract title, date, PDF URL from listing
  - Download PDF and extract text using pdfplumber
  - Parse date from PDF filename pattern: G-YYYY-MM-DD.pdf

Source: https://sajurin.enriquebolanos.org/
Rate limit: 1 req/sec

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
from urllib.parse import urljoin

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

SOURCE_ID = "NI/SajurinGacetas"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NI.SajurinGacetas")

BASE_URL = "https://sajurin.enriquebolanos.org"
GACETA_LIST_URL = (
    f"{BASE_URL}/?icontainer=5602cabdf0058cf70234a2ee"
    "&q=&item_5602cabdf0058cf70234a2ee=593fb5583a4b300b5a29c0a6"
    "&index=595cb8ca1903640cdf27aef1"
    "&indexmap=595cba8e1903640cdf27aef2"
    "&gacetayear_filter=&_view=internal"
)

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
    "Accept-Language": "es,en",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

RATE_LIMIT = 1.5
_last_request = 0.0


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


def parse_date_from_filename(filename):
    """Extract date from G-YYYY-MM-DD.pdf pattern."""
    match = re.search(r"G-(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def parse_date_from_title(title):
    """Try to parse date from gazette title like 'No. 50 del 12 de marzo 1999'."""
    months_es = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
    }
    match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+(\d{4})", title)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2).lower()
        year = match.group(3)
        month = months_es.get(month_name)
        if month:
            return f"{year}-{month}-{day}"
    return None


def extract_pdf_text(pdf_bytes, max_pages=None):
    """Extract text from PDF bytes using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages
            if max_pages:
                pages = pages[:max_pages]
            texts = []
            for page in pages:
                text = page.extract_text() or ""
                if text.strip():
                    texts.append(text.strip())
            return "\n\n".join(texts)
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def get_listing_page(page_num):
    """Fetch a listing page and return gazette metadata."""
    url = GACETA_LIST_URL + f"&page={page_num}"
    logger.info(f"Fetching listing page {page_num}")
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    pdf_links = soup.find_all("a", href=lambda x: x and ".pdf" in str(x))
    for link in pdf_links:
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or not href:
            continue
        # Skip non-gazette links
        if "gaceta" not in title.lower() and "G-" not in href:
            continue

        full_url = urljoin(BASE_URL, href)

        # Parse date
        date = parse_date_from_filename(href)
        if not date:
            date = parse_date_from_title(title)

        # Generate ID from filename
        filename = href.split("/")[-1].replace(".pdf", "")
        gazette_id = re.sub(r"[^\w\-]", "_", filename)

        items.append({
            "gazette_id": gazette_id,
            "title": title,
            "pdf_url": full_url,
            "date": date,
        })

    return items


def fetch_all(sample=False):
    """Fetch gazette issues."""
    max_pages = 2 if sample else 1348  # 1348 pages total
    max_docs = 15 if sample else None

    count = 0
    seen_ids = set()

    for page_num in range(1, max_pages + 1):
        try:
            items = get_listing_page(page_num)
        except Exception as e:
            logger.error(f"Error on page {page_num}: {e}")
            continue

        if not items:
            logger.info(f"No items on page {page_num}, stopping")
            break

        for item in items:
            if item["gazette_id"] in seen_ids:
                continue
            seen_ids.add(item["gazette_id"])

            # Download and extract PDF
            try:
                logger.info(f"Downloading: {item['pdf_url']}")
                pdf_resp = _get(item["pdf_url"])
                text = extract_pdf_text(pdf_resp.content)

                if not text or len(text) < 50:
                    logger.warning(f"Skipping {item['gazette_id']}: no text extracted")
                    continue

                record = {
                    "_id": item["gazette_id"],
                    "_source": SOURCE_ID,
                    "_type": "legislation",
                    "_fetched_at": datetime.now(timezone.utc).isoformat(),
                    "title": item["title"],
                    "text": text,
                    "date": item["date"],
                    "url": item["pdf_url"],
                    "language": "es",
                    "gazette_id": item["gazette_id"],
                    "page_count": None,
                }

                # Get page count
                try:
                    with pdfplumber.open(io.BytesIO(pdf_resp.content)) as pdf:
                        record["page_count"] = len(pdf.pages)
                except Exception:
                    pass

                yield record
                count += 1
                logger.info(f"[{count}] {item['title'][:50]} — {len(text)} chars")

                if max_docs and count >= max_docs:
                    return

            except Exception as e:
                logger.error(f"Error downloading {item['pdf_url']}: {e}")
                continue

    logger.info(f"Total gazette issues fetched: {count}")


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
    print(f"Testing {BASE_URL} ...")
    resp = _get(GACETA_LIST_URL)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    pdf_links = soup.find_all("a", href=lambda x: x and ".pdf" in str(x))
    gaceta_links = [l for l in pdf_links if "gaceta" in l.get_text(strip=True).lower() or "G-" in l.get("href", "")]
    print(f"Gaceta PDF links on page 1: {len(gaceta_links)}")
    for l in gaceta_links[:3]:
        print(f"  - {l.get_text(strip=True)[:60]} -> {l['href'][:60]}")

    # Test PDF download
    if gaceta_links:
        pdf_url = urljoin(BASE_URL, gaceta_links[0]["href"])
        print(f"\nTesting PDF download: {pdf_url}")
        pdf_resp = _get(pdf_url)
        print(f"PDF size: {len(pdf_resp.content)} bytes")
        text = extract_pdf_text(pdf_resp.content, max_pages=1)
        print(f"Page 1 text: {len(text)} chars")
        if text:
            print(f"Sample: {text[:200]}")

    print("\nAPI test passed." if gaceta_links else "WARNING: No gaceta links found!")


def main():
    parser = argparse.ArgumentParser(description="NI/SajurinGacetas bootstrapper")
    parser.add_argument("command", choices=["test-api", "bootstrap"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
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
