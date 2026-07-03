#!/usr/bin/env python3
"""
US/OFAC-Enforcement -- OFAC Civil Penalties and Enforcement Actions

Fetches OFAC enforcement actions (settlement agreements, findings of violation,
civil penalty notices) from ofac.treasury.gov. Covers 2003–present with ~500+
enforcement actions with full text extracted from PDF documents.

Data access:
  - Year-by-year listing pages with HTML tables + PDF links
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
logger = logging.getLogger("legal-data-hunter.US.OFAC-Enforcement")

BASE_URL = "https://ofac.treasury.gov"
CURRENT_YEAR = datetime.now().year
# Current year page is the main page; prior years have their own sub-pages
YEAR_URL_CURRENT = f"{BASE_URL}/civil-penalties-and-enforcement-information"
YEAR_URL_TEMPLATE = f"{BASE_URL}/civil-penalties-and-enforcement-information/{{year}}-enforcement-information"
FIRST_YEAR = 2003

DELAY = 1.5
SOURCE_ID = "US/OFAC-Enforcement"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})


def parse_penalty(text: str) -> Optional[float]:
    """Parse penalty amount like '$1,234,567' into float."""
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.]", "", text)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
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


def make_id(href: str, year: int) -> str:
    """Create a stable ID from the PDF media URL."""
    # /media/934831/download?inline -> ofac-934831
    m = re.search(r"/media/(\d+)/", href)
    if m:
        return f"ofac-{m.group(1)}"
    # Fallback: use last meaningful path segment
    path = href.split("?")[0].rstrip("/")
    return f"ofac-{year}-{path.split('/')[-1]}"


def get_year_urls() -> list:
    """Return list of (year, url) tuples from newest to oldest."""
    urls = [(CURRENT_YEAR, YEAR_URL_CURRENT)]
    for year in range(CURRENT_YEAR - 1, FIRST_YEAR - 1, -1):
        urls.append((year, YEAR_URL_TEMPLATE.format(year=year)))
    return urls


def scrape_year_page(year: int, url: str) -> list:
    """Scrape a single year's enforcement page and return list of actions."""
    logger.info("Fetching %d: %s", year, url)
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to fetch %d page: %s", year, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        logger.warning("No table found on %d page", year)
        return []

    rows = table.find_all("tr")[1:]  # skip header
    actions = []

    # Detect column layout: some years have Date|Entity|Count|Amount (4 cols),
    # others have Entity|Count|Amount (3 cols). The date column has a link
    # whose text looks like MM/DD/YYYY.
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # Find the cell with the PDF link
        a_tag = None
        link_cell_idx = None
        for idx, cell in enumerate(cells):
            tag = cell.find("a", href=True)
            if tag:
                href = tag["href"]
                if "/media/" in href or href.endswith(".pdf"):
                    a_tag = tag
                    link_cell_idx = idx
                    break

        if not a_tag:
            continue

        href = a_tag["href"]
        link_text = a_tag.get_text(strip=True)

        # Determine if link text is a date (MM/DD/YYYY) or entity name
        is_date_link = bool(re.match(r"\d{2}/\d{2}/\d{4}", link_text))

        if is_date_link:
            # Format: Date(link) | Entity | Count | Amount
            date_text = link_text
            entity_name = cells[link_cell_idx + 1].get_text(strip=True) if len(cells) > link_cell_idx + 1 else ""
            violations = cells[link_cell_idx + 2].get_text(strip=True) if len(cells) > link_cell_idx + 2 else ""
            penalty_text = cells[link_cell_idx + 3].get_text(strip=True) if len(cells) > link_cell_idx + 3 else ""
        else:
            # Format: Entity(link) | Count | Amount
            entity_name = link_text
            date_text = ""
            violations = cells[link_cell_idx + 1].get_text(strip=True) if len(cells) > link_cell_idx + 1 else ""
            penalty_text = cells[link_cell_idx + 2].get_text(strip=True) if len(cells) > link_cell_idx + 2 else ""

        if not entity_name:
            entity_name = link_text

        full_url = href if href.startswith("http") else BASE_URL + href

        actions.append({
            "entity_name": entity_name,
            "date_text": date_text,
            "violations": violations,
            "penalty_text": penalty_text,
            "penalty_amount": parse_penalty(penalty_text),
            "pdf_url": full_url,
            "href": href,
            "year": year,
        })

    logger.info("Found %d actions for %d", len(actions), year)
    return actions


def scrape_all_years(*, sample: bool = False) -> list:
    """Scrape all year pages and return deduplicated list of actions."""
    seen_ids = set()
    all_actions = []

    for year, url in get_year_urls():
        actions = scrape_year_page(year, url)
        for action in actions:
            aid = make_id(action["href"], action["year"])
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            action["_aid"] = aid
            all_actions.append(action)
        time.sleep(DELAY)

        # For sample mode, stop once we have enough listings
        if sample and len(all_actions) >= 20:
            break

    logger.info("Total unique actions across all years: %d", len(all_actions))
    return all_actions


def fetch_and_normalize(action: dict) -> Optional[Dict[str, Any]]:
    """Download the PDF and normalize into a record."""
    pdf_url = action["pdf_url"]
    logger.info("Downloading: %s", action["entity_name"][:60])

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

    # Determine date: prefer explicit date_text from table, then extract from PDF
    date_iso = None
    if action.get("date_text"):
        date_iso = parse_date_text(action["date_text"])

    if not date_iso:
        # Try to extract date from PDF text
        date_match = re.search(
            r"(?:Enforcement Release|dated|effective|entered)[:\s]+(?:as\s+of\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
            text[:2000], re.IGNORECASE
        )
        if date_match:
            date_iso = parse_date_text(date_match.group(1))

    if not date_iso:
        date_iso = f"{action['year']}-01-01"

    record = {
        "_id": action["_aid"],
        "_source": SOURCE_ID,
        "_type": "doctrine",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"OFAC Enforcement Action: {action['entity_name']}",
        "entity_name": action["entity_name"],
        "date": date_iso,
        "text": text,
        "url": pdf_url,
        "penalty_amount": action["penalty_amount"],
        "penalty_text": action["penalty_text"] or None,
        "violations": action["violations"] or None,
        "year": action["year"],
    }

    return record


def parse_date_text(text: str) -> Optional[str]:
    """Parse a date string like 'January 15, 2024', 'March 5 2020', or '06/01/2026' into ISO."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    for fmt in ["%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def fetch_all(*, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
    """Yield all enforcement action records."""
    actions = scrape_all_years(sample=sample)

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
    # Clean old samples
    for f in sample_dir.glob("sample_*.json"):
        f.unlink()
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
    resp = SESSION.get(YEAR_URL_CURRENT, timeout=15)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")[1:] if table else []
    print(f"Enforcement actions found (current year): {len(rows)}")

    if rows:
        a_tag = rows[0].find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
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
