#!/usr/bin/env python3
"""
US/FLRA -- Federal Labor Relations Authority Decisions

Fetches FLRA Authority decisions from flra.gov.
~10,400 decisions with full text from HTML detail pages.

Data access:
  - Listing pages at /decisions/authority-decisions?page=N (10 per page)
  - Individual decision HTML pages at /decisions/v{vol}/{vol}-{num}
  - Plain HTTP requests (no Playwright needed)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
import html as htmlmod
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.FLRA")

BASE_URL = "https://www.flra.gov"
LISTING_URL = BASE_URL + "/decisions/authority-decisions"
DELAY = 1.5
SOURCE_ID = "US/FLRA"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})


def parse_date(date_str: str) -> Optional[str]:
    """Parse FLRA date formats like 'Jun. 03, 2026' into ISO 8601."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Remove header text that may be stuck to the date
    date_str = re.sub(r"^(Issuance Date|Date)\s*", "", date_str)
    for fmt in ["%b. %d, %Y", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def clean_text(text: str) -> str:
    """Clean extracted text."""
    text = htmlmod.unescape(text)
    text = re.sub(r"\xa0", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_html(html_content: str) -> str:
    """Extract clean text from an HTML decision page."""
    # Find article tag
    article = re.search(r"<article[^>]*>(.*?)</article>", html_content, re.DOTALL)
    if not article:
        return ""
    content = article.group(1)
    # Remove script/style
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
    content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
    # Replace block tags with newlines
    content = re.sub(r"<(?:p|br|div|h[1-6]|li|tr)[^>]*/?>", "\n", content)
    # Remove all remaining tags
    content = re.sub(r"<[^>]+>", "", content)
    return clean_text(content)


def parse_listing_page(html_content: str) -> List[Dict[str, str]]:
    """Parse a listing page and extract decision metadata from paired rows."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
    except ImportError:
        return _parse_listing_regex(html_content)

    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    entries = []
    i = 1  # skip header row

    while i < len(rows) - 1:
        meta_row = rows[i]
        links_row = rows[i + 1]

        meta_cells = meta_row.find_all("td")
        links_cells = links_row.find_all("td")

        if len(meta_cells) < 5:
            i += 1
            continue

        citation = meta_cells[0].get_text(strip=True)
        # Remove header text prefix
        citation = re.sub(r"^Citation\s*#?\s*", "", citation)
        issuance_num = meta_cells[1].get_text(strip=True)
        issuance_num = re.sub(r"^Issuance\s*#?\s*", "", issuance_num)
        issuance_date = meta_cells[2].get_text(strip=True)
        issuance_date = re.sub(r"^Issuance\s*Date\s*", "", issuance_date)
        case_number = meta_cells[3].get_text(strip=True)
        case_number = re.sub(r"^Case\s*#?\s*", "", case_number)
        arbitrator = meta_cells[4].get_text(strip=True)
        arbitrator = re.sub(r"^Arbitrator\s*", "", arbitrator)

        # Extract links from second row
        html_url = ""
        parties = ""
        if links_cells:
            # First cell has PDF/HTML/Digest links
            for a in links_cells[0].find_all("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if text == "HTML" and "/decisions/v" in href:
                    html_url = href if href.startswith("http") else BASE_URL + href
                    break
            # Second cell has parties
            if len(links_cells) > 1:
                parties = links_cells[1].get_text(strip=True)

        if html_url:
            entries.append({
                "citation": citation,
                "issuance_number": issuance_num,
                "date": issuance_date,
                "case_number": case_number,
                "arbitrator": arbitrator,
                "html_url": html_url,
                "parties": parties,
            })

        i += 2

    return entries


def _parse_listing_regex(html_content: str) -> List[Dict[str, str]]:
    """Fallback regex parser when bs4 is not available."""
    entries = []
    # Find all HTML decision links
    html_links = re.findall(
        r'href="((?:https://www\.flra\.gov)?/decisions/v\d+/\d+-\d+)"',
        html_content,
    )
    for link in html_links:
        url = link if link.startswith("http") else BASE_URL + link
        # Extract volume/number from URL
        m = re.search(r"/v(\d+)/(\d+)-(\d+)", url)
        if m:
            vol, num = m.group(1), m.group(3)
            entries.append({
                "citation": f"{vol} FLRA No. {num}",
                "issuance_number": num,
                "date": "",
                "case_number": "",
                "arbitrator": "",
                "html_url": url,
                "parties": "",
            })
    return entries


class FLRAScraper:
    SOURCE_ID = SOURCE_ID

    def _get(self, url: str, retries: int = 3) -> Optional[str]:
        """HTTP GET with retries."""
        for attempt in range(retries):
            try:
                resp = SESSION.get(url, timeout=30)
                if resp.status_code == 200:
                    return resp.text
                logger.warning("HTTP %d for %s", resp.status_code, url)
            except requests.RequestException as e:
                logger.warning("Request error for %s: %s (attempt %d)", url, e, attempt + 1)
            if attempt < retries - 1:
                time.sleep(DELAY * (attempt + 1))
        return None

    def get_total_count(self) -> int:
        """Get total number of authority decisions."""
        html = self._get(LISTING_URL)
        if not html:
            return 0
        m = re.search(r"Displaying \d+ - \d+ of (\d[\d,]*)", html)
        return int(m.group(1).replace(",", "")) if m else 0

    def collect_listings(self, max_pages: int = 0) -> Generator[Dict[str, str], None, None]:
        """Paginate through listing pages and yield decision entries."""
        page = 0
        seen_urls = set()

        while True:
            url = f"{LISTING_URL}?page={page}"
            logger.info("Fetching listing page %d: %s", page, url)
            html = self._get(url)
            if not html:
                break

            entries = parse_listing_page(html)
            if not entries:
                logger.info("No more entries on page %d", page)
                break

            new_count = 0
            for entry in entries:
                if entry["html_url"] not in seen_urls:
                    seen_urls.add(entry["html_url"])
                    new_count += 1
                    yield entry

            if new_count == 0:
                break

            page += 1
            if max_pages and page >= max_pages:
                break

            time.sleep(DELAY)

    def fetch_decision_text(self, url: str) -> str:
        """Fetch full text from an individual decision page."""
        html = self._get(url)
        if not html:
            return ""
        return extract_text_from_html(html)

    def normalize(self, listing: Dict[str, str], text: str) -> Dict[str, Any]:
        """Normalize into standard schema."""
        url = listing["html_url"]
        # Build ID from URL path: /decisions/v74/74-67 -> flra-v74-67
        m = re.search(r"/decisions/v(\d+)/(\d+)-(\d+)", url)
        if m:
            doc_id = f"flra-v{m.group(1)}-{m.group(3)}"
        else:
            slug = url.rstrip("/").split("/")[-1]
            doc_id = f"flra-{slug}"

        date = parse_date(listing.get("date", ""))
        title = listing.get("parties", "") or listing.get("citation", doc_id)

        return {
            "_id": doc_id,
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url,
            "citation": listing.get("citation", ""),
            "case_number": listing.get("case_number", ""),
            "arbitrator": listing.get("arbitrator", ""),
            "issuance_number": listing.get("issuance_number", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Fetch all decisions (or a sample)."""
        max_pages = 2 if sample else 0
        count = 0

        for listing in self.collect_listings(max_pages=max_pages):
            logger.info("Fetching decision: %s", listing.get("citation", listing["html_url"]))
            time.sleep(DELAY)

            text = self.fetch_decision_text(listing["html_url"])
            if not text:
                logger.warning("No text for %s, skipping", listing["html_url"])
                continue

            record = self.normalize(listing, text)
            if record["text"]:
                yield record
                count += 1

            if sample and count >= 15:
                break

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch decisions issued since a date."""
        since_dt = datetime.fromisoformat(since)

        for listing in self.collect_listings(max_pages=20):
            date = parse_date(listing.get("date", ""))
            if date and datetime.fromisoformat(date) < since_dt:
                logger.info("Reached decisions before %s, stopping", since)
                break

            logger.info("Fetching update: %s", listing.get("citation", ""))
            time.sleep(DELAY)

            text = self.fetch_decision_text(listing["html_url"])
            if not text:
                continue
            record = self.normalize(listing, text)
            if record["text"]:
                yield record

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        html = self._get(LISTING_URL)
        if not html:
            return False
        total = re.search(r"Displaying \d+ - \d+ of (\d[\d,]*)", html)
        if total:
            logger.info("Connection OK: %s total decisions", total.group(1))
            return True
        return False


def save_samples(records: List[Dict[str, Any]], sample_dir: Path):
    sample_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        fname = re.sub(r"[^a-zA-Z0-9_-]", "_", rec["_id"])[:80] + ".json"
        path = sample_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d samples to %s", len(records), sample_dir)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0]
    # NOTE: bootstrap-fast does a FULL run (not sample). Only --sample limits
    # to 15. Previously bootstrap-fast forced sample mode and the full path
    # wrote output.jsonl, so the VPS pipeline found no data/records.jsonl and
    # ingested only the 15 committed samples then exited 1 (#981, #859 class).
    sample_mode = "--sample" in args
    source_dir = Path(__file__).parent
    sample_dir = source_dir / "sample"
    data_dir = source_dir / "data"

    scraper = FLRAScraper()

    if command == "test":
        ok = scraper.test_connection()
        print("OK" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        if sample_mode:
            records = []
            for record in scraper.fetch_all(sample=True):
                records.append(record)
                logger.info(
                    "Record %d: %s (%d chars)",
                    len(records), record["_id"], len(record["text"]),
                )
                if len(records) >= 15:
                    break
            save_samples(records, sample_dir)
            avg = sum(len(r["text"]) for r in records) // max(len(records), 1)
            logger.info("Done: %d sample records, avg text length: %d chars",
                        len(records), avg)
        else:
            # Full run: stream every record to data/records.jsonl as we go.
            data_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"
            count = 0
            total_chars = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in scraper.fetch_all(sample=False):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    total_chars += len(record["text"])
                    if count % 50 == 0:
                        logger.info("Progress: %d records written", count)
            logger.info(
                "Full bootstrap complete: %d records -> %s (avg %d chars)",
                count, jsonl_path, total_chars // max(count, 1))

        logger.info(
            "Done.",
        )

    elif command == "update":
        since = args[1] if len(args) > 1 else "2026-01-01"
        records = list(scraper.fetch_updates(since))
        out_path = source_dir / "updates.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info("Wrote %d update records to %s", len(records), out_path)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
