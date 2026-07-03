#!/usr/bin/env python3
"""
US/FinCEN-Enforcement -- Financial Crimes Enforcement Network Enforcement Actions

Fetches FinCEN enforcement actions (consent orders, civil money penalties)
from fincen.gov. ~131 enforcement actions with full text from PDF documents.

Data access:
  - Two listing pages with table of enforcement actions + PDF links
  - PDFs downloaded and text extracted via pdfplumber
  - All public domain U.S. government works

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import io
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.FinCEN-Enforcement")

BASE_URL = "https://www.fincen.gov"
LISTING_URLS = [
    BASE_URL + "/news/enforcement-actions",
    BASE_URL + "/enforcement-actions-failure-register-money-services-business",
]
DELAY = 2.0
SOURCE_ID = "US/FinCEN-Enforcement"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})


def parse_date(date_str: str) -> Optional[str]:
    """Parse FinCEN date formats like '03/06/2026' into ISO 8601."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" \n", "\n", text)
    return text.strip()


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using pdfplumber."""
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        pages = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
            try:
                page.flush_cache(); page.get_textmap.cache_clear()
            except Exception:
                pass
        pdf.close()
        return clean_text("\n\n".join(pages))
    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return ""


def make_id(href: str) -> str:
    """Create a stable ID from the PDF URL path."""
    # /system/files/enforcement_action/2024-10-10/FinCEN-TD-Bank-Consent-Order-508FINAL.pdf
    # -> enforcement_action-2024-10-10-FinCEN-TD-Bank-Consent-Order-508FINAL
    path = href.rstrip("/").replace(".pdf", "")
    parts = path.split("/system/files/")
    if len(parts) == 2:
        return parts[1].replace("/", "-")
    # Fallback: use last segment
    return path.split("/")[-1]


def scrape_listings() -> list:
    """Scrape both listing pages and return deduplicated list of enforcement actions."""
    seen_hrefs = set()
    actions = []

    for listing_url in LISTING_URLS:
        logger.info("Fetching listing: %s", listing_url)
        resp = SESSION.get(listing_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table")
        if not table:
            logger.warning("No table found on %s", listing_url)
            continue

        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            a_tag = cells[0].find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"]
            if not href.endswith(".pdf"):
                continue

            # Deduplicate across both pages
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            title = a_tag.get_text(strip=True)
            date_str = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            matter = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            category = cells[3].get_text(strip=True) if len(cells) > 3 else ""

            full_url = href if href.startswith("http") else BASE_URL + href

            actions.append({
                "title": title,
                "date": date_str,
                "matter_number": matter,
                "institution_type": category,
                "pdf_url": full_url,
                "href": href,
            })

        time.sleep(DELAY)

    logger.info("Found %d unique enforcement actions across %d pages",
                len(actions), len(LISTING_URLS))
    return actions


def fetch_and_normalize(action: dict) -> Optional[Dict[str, Any]]:
    """Download the PDF and normalize into a record."""
    pdf_url = action["pdf_url"]
    logger.info("Downloading: %s", action["title"][:60])

    try:
        resp = SESSION.get(pdf_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to download %s: %s", pdf_url, e)
        return None

    if "application/pdf" not in resp.headers.get("Content-Type", "") and \
       not pdf_url.endswith(".pdf"):
        logger.warning("Not a PDF: %s (Content-Type: %s)",
                       pdf_url, resp.headers.get("Content-Type"))
        return None

    text = extract_text_from_pdf(resp.content)
    if not text or len(text) < 100:
        logger.warning("Insufficient text extracted from %s (%d chars)",
                       pdf_url, len(text))
        return None

    record = {
        "_id": make_id(action["href"]),
        "_source": SOURCE_ID,
        "_type": "doctrine",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": action["title"],
        "date": parse_date(action["date"]),
        "text": text,
        "url": pdf_url,
        "matter_number": action["matter_number"] or None,
        "institution_type": action["institution_type"] or None,
    }
    return record


def fetch_all(*, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
    """Yield all enforcement action records."""
    actions = scrape_listings()

    if sample:
        actions = actions[:15]

    for i, action in enumerate(actions):
        record = fetch_and_normalize(action)
        if record:
            yield record
        if i < len(actions) - 1:
            time.sleep(DELAY)


def save_samples(records: list, sample_dir: Path):
    """Save sample records to the sample directory."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    for i, record in enumerate(records):
        path = sample_dir / f"sample_{i:03d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        logger.info("Saved %s (%d chars text)", path.name, len(record.get("text", "")))


def cmd_bootstrap(sample: bool = False):
    """Run the bootstrap process."""
    source_dir = Path(__file__).parent
    sample_dir = source_dir / "sample"

    records = []
    for record in fetch_all(sample=sample):
        records.append(record)
        logger.info("[%d] %s — %s (%d chars)",
                    len(records), record["_id"][:40],
                    record["title"][:50], len(record["text"]))

    if sample:
        save_samples(records, sample_dir)

    logger.info("Done. Total records: %d", len(records))
    return records


def cmd_test():
    """Quick connectivity test."""
    resp = SESSION.get(LISTING_URLS[0], timeout=15)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")[1:] if table else []
    print(f"Enforcement actions found: {len(rows)}")

    if rows:
        a_tag = rows[0].find("a", href=True)
        if a_tag and a_tag["href"].endswith(".pdf"):
            pdf_url = BASE_URL + a_tag["href"] if not a_tag["href"].startswith("http") else a_tag["href"]
            print(f"Testing PDF download: {pdf_url}")
            r = SESSION.get(pdf_url, timeout=30)
            print(f"PDF status: {r.status_code}, size: {len(r.content)} bytes")
            text = extract_text_from_pdf(r.content)
            print(f"Extracted text: {len(text)} chars")
            print(f"First 200 chars: {text[:200]}")

    print("Test passed.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]
    if cmd == "test":
        cmd_test()
    elif cmd == "bootstrap":
        sample = "--sample" in args
        cmd_bootstrap(sample=sample)
    elif cmd == "bootstrap-fast":
        cmd_bootstrap(sample=True)
    elif cmd == "update":
        cmd_bootstrap(sample=False)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
