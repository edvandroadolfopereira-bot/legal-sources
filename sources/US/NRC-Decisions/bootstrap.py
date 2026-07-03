#!/usr/bin/env python3
"""
US/NRC-Decisions -- Nuclear Regulatory Commission Adjudicatory Decisions

Fetches Commission orders (CLI-*) and ASLBP orders (LBP-*) from nrc.gov.
~750 decisions with full text extracted from PDF documents.

Data access:
  - Year index pages list decisions in HTML tables with PDF links
  - Commission orders: /reading-rm/doc-collections/commission/orders/{YEAR}/
  - ASLBP orders: /reading-rm/doc-collections/aslbp/orders/{YEAR}/
  - PDFs hosted at /docs/ML{...}/{ACCESSION}.pdf

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
from typing import Generator, Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup
import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.NRC-Decisions")

BASE_URL = "https://www.nrc.gov"
COMMISSION_INDEX = BASE_URL + "/reading-rm/doc-collections/commission/orders/index.html"
ASLBP_INDEX = BASE_URL + "/reading-rm/doc-collections/aslbp/orders/index.html"
DELAY = 2.0
SOURCE_ID = "US/NRC-Decisions"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})
MAX_RETRIES = 3
TIMEOUT = 60


def robust_get(url: str, timeout: int = TIMEOUT) -> requests.Response:
    """GET with retry logic for slow NRC servers."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = (attempt + 1) * 5
                logger.warning("Retry %d/%d for %s: %s (waiting %ds)",
                               attempt + 1, MAX_RETRIES, url, e, wait)
                time.sleep(wait)
            else:
                raise


def parse_date(date_str: str) -> Optional[str]:
    """Parse NRC date like '11/20/2024' or '08/27/24' into ISO 8601."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Extract date pattern from mixed text like '11/20/202450-611-CP'
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", date_str)
    if not m:
        return None
    d = m.group(1)
    for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
        try:
            return datetime.strptime(d, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_docket(text: str) -> Optional[str]:
    """Extract docket number from the date/docket cell text."""
    if not text:
        return None
    # Remove date portion
    cleaned = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", "", text).strip()
    return cleaned if cleaned else None


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


def get_years(index_url: str) -> List[int]:
    """Get list of available years from an index page."""
    resp = SESSION.get(index_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    years = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip("/")
        parts = href.split("/")
        for p in parts:
            if p.isdigit() and 1990 <= int(p) <= 2030:
                years.add(int(p))
    return sorted(years, reverse=True)


def scrape_year_page(year_url: str, decision_type: str) -> List[Dict]:
    """Scrape a single year page and return list of decision metadata."""
    resp = SESSION.get(year_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    decisions = []
    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # First cell: decision number with PDF link
        a_tag = cells[0].find("a", href=True)
        if not a_tag or not a_tag["href"].endswith(".pdf"):
            continue

        decision_num = a_tag.get_text(strip=True)
        pdf_href = a_tag["href"]
        full_pdf_url = pdf_href if pdf_href.startswith("http") else BASE_URL + pdf_href

        # Second cell: licensee/party name
        licensee = cells[1].get_text(strip=True) if len(cells) > 1 else ""

        # Third cell: date + docket number (merged)
        date_docket = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        date = parse_date(date_docket)
        docket = extract_docket(date_docket)

        title = f"{decision_num} — {licensee}" if licensee else decision_num

        decisions.append({
            "decision_number": decision_num,
            "title": title,
            "licensee": licensee,
            "date": date,
            "docket_number": docket,
            "pdf_url": full_pdf_url,
            "decision_type": decision_type,
        })

    return decisions


def scrape_all_listings(*, sample: bool = False) -> List[Dict]:
    """Scrape both Commission and ASLBP year pages."""
    all_decisions = []

    for index_url, prefix, dtype in [
        (COMMISSION_INDEX, "/reading-rm/doc-collections/commission/orders", "commission_order"),
        (ASLBP_INDEX, "/reading-rm/doc-collections/aslbp/orders", "aslbp_order"),
    ]:
        logger.info("Fetching index: %s", index_url)
        years = get_years(index_url)
        logger.info("Found %d years for %s", len(years), dtype)
        time.sleep(DELAY)

        for year in years:
            year_url = f"{BASE_URL}{prefix}/{year}/"
            logger.info("Scraping %s %d", dtype, year)
            decisions = scrape_year_page(year_url, dtype)
            all_decisions.extend(decisions)
            logger.info("  Found %d decisions", len(decisions))
            time.sleep(DELAY)

            if sample and len(all_decisions) >= 20:
                break

        if sample and len(all_decisions) >= 20:
            break

    logger.info("Total decisions found: %d", len(all_decisions))
    return all_decisions


def fetch_and_normalize(decision: dict) -> Optional[Dict[str, Any]]:
    """Download the PDF and normalize into a record."""
    pdf_url = decision["pdf_url"]
    logger.info("Downloading: %s", decision["decision_number"])

    try:
        resp = SESSION.get(pdf_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to download %s: %s", pdf_url, e)
        return None

    text = extract_text_from_pdf(resp.content)
    if not text or len(text) < 100:
        logger.warning("Insufficient text from %s (%d chars)", pdf_url, len(text))
        return None

    record = {
        "_id": decision["decision_number"],
        "_source": SOURCE_ID,
        "_type": "case_law",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": decision["title"],
        "date": decision["date"],
        "text": text,
        "url": pdf_url,
        "decision_number": decision["decision_number"],
        "decision_type": decision["decision_type"],
        "licensee": decision["licensee"] or None,
        "docket_number": decision["docket_number"] or None,
    }
    return record


def fetch_all(*, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
    """Yield all NRC decision records."""
    decisions = scrape_all_listings(sample=sample)

    if sample:
        decisions = decisions[:15]

    for i, decision in enumerate(decisions):
        record = fetch_and_normalize(decision)
        if record:
            yield record
        if i < len(decisions) - 1:
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
                    len(records), record["_id"],
                    record["title"][:50], len(record["text"]))

    if sample:
        save_samples(records, sample_dir)

    logger.info("Done. Total records: %d", len(records))
    return records


def cmd_test():
    """Quick connectivity test."""
    resp = SESSION.get(COMMISSION_INDEX, timeout=15)
    print(f"Commission index status: {resp.status_code}")
    years = get_years(COMMISSION_INDEX)
    print(f"Commission years: {len(years)} ({years[0]}–{years[-1]})")

    resp2 = SESSION.get(ASLBP_INDEX, timeout=15)
    print(f"ASLBP index status: {resp2.status_code}")
    years2 = get_years(ASLBP_INDEX)
    print(f"ASLBP years: {len(years2)} ({years2[0]}–{years2[-1]})")

    # Test one PDF
    decisions = scrape_year_page(f"{BASE_URL}/reading-rm/doc-collections/commission/orders/{years[0]}/", "commission_order")
    if decisions:
        d = decisions[0]
        print(f"\nTest PDF: {d['decision_number']} — {d['pdf_url']}")
        r = SESSION.get(d["pdf_url"], timeout=30)
        print(f"PDF status: {r.status_code}, size: {len(r.content)} bytes")
        text = extract_text_from_pdf(r.content)
        print(f"Extracted text: {len(text)} chars")
        print(f"First 200 chars: {text[:200]}")

    print("\nTest passed.")


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
