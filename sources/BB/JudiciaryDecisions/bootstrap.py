#!/usr/bin/env python3
"""
BB/JudiciaryDecisions -- Barbados Judiciary Court Judgments

Fetches judgments from the Barbados Judicial System website
(barbadoslawcourts.gov.bb), covering Court of Appeal, High Court,
Magistrate's Courts and Registrar's Taxation Decisions (2007-2022).

Strategy:
  1. GET search results pages from case-search-results/ endpoint
     (all courts, paginated, 10 per page, ~82 pages / ~814 judgments).
  2. Parse the HTML table to extract metadata (title, court, judge, date,
     PDF URL, detail page slug).
  3. Fetch each detail page and extract full judgment text from the
     <section class="pdf-content"> element.
  4. Strip HTML tags to produce clean text.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Same as bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import re
import time
import html
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BB.JudiciaryDecisions")

BASE_URL = "https://www.barbadoslawcourts.gov.bb"
SEARCH_URL = BASE_URL + "/case-search-results/"

# Regex patterns for parsing the results table
ROW_RE = re.compile(
    r'<tr>\s*<td[^>]*>.*?</td>\s*'               # checkbox column
    r'<td[^>]*>\s*<p>\d+\.\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a></p>'  # link + title
    r'.*?<span class="advsea-extract">([^<]*)</span>.*?'  # extract/snippet
    r'</td>\s*<td[^>]*>([^<]*)</td>\s*'            # court
    r'<td>([^<]*)</td>.*?'                          # judge
    r'<td>(\d{2}/\d{2}/\d{4})</td>\s*'             # date
    r'<td[^>]*>\s*<a\s+href="([^"]*)"',            # PDF link
    re.DOTALL
)

TAG_RE = re.compile(r'<[^>]+>')
MULTI_WS_RE = re.compile(r'\s+')


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = TAG_RE.sub(' ', text)
    text = html.unescape(text)
    text = MULTI_WS_RE.sub(' ', text)
    return text.strip()


def parse_date(date_str: str) -> Optional[str]:
    """Parse DD/MM/YYYY to ISO 8601."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


class BarbadosJudiciaryScraper(BaseScraper):
    SOURCE_ID = "BB/JudiciaryDecisions"

    def __init__(self):
        super().__init__(str(Path(__file__).resolve().parent))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; +https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def fetch_all(self, sample: bool = False) -> Generator[Dict, None, None]:
        """Yield all judgment records."""
        max_records = 15 if sample else 10000
        count = 0
        page = 1

        while count < max_records:
            logger.info(f"Fetching search results page {page}...")
            entries = self._fetch_results_page(page)
            if not entries:
                logger.info(f"No results on page {page}, stopping.")
                break

            for entry in entries:
                if count >= max_records:
                    break

                record = self._fetch_detail(entry)
                if record and record.get("text") and len(record["text"]) >= 200:
                    yield record
                    count += 1
                    if count % 10 == 0:
                        logger.info(f"Fetched {count} records so far...")
                else:
                    logger.warning(f"Skipping {entry.get('title', '?')}: insufficient text")

                time.sleep(1.5)

            page += 1
            time.sleep(1.0)

        logger.info(f"Total records fetched: {count}")

    def fetch_updates(self, since: Optional[str] = None) -> Generator[Dict, None, None]:
        """Yield documents modified since a date."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict) -> Dict:
        """Already normalized during fetch."""
        return raw

    def _fetch_results_page(self, page: int) -> list:
        """Fetch a single page of search results and parse entries."""
        params = {
            "q": "case-search-results/",
            "asId": "as0",
            "court[0]": "all",
            "page": str(page),
        }
        try:
            resp = self.session.get(SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch results page {page}: {e}")
            return []

        entries = []
        for m in ROW_RE.finditer(resp.text):
            slug = m.group(1).strip().rstrip('/')
            title = html.unescape(m.group(2).strip())
            court = m.group(4).strip()
            judge = m.group(5).strip()
            date_str = m.group(6).strip()
            pdf_path = m.group(7).strip()

            entries.append({
                "slug": slug,
                "title": title,
                "court": court,
                "judge": judge,
                "date_raw": date_str,
                "pdf_url": BASE_URL + "/" + pdf_path.lstrip("/") if pdf_path else None,
            })

        logger.info(f"Page {page}: found {len(entries)} entries")
        return entries

    def _fetch_detail(self, entry: dict) -> Optional[Dict]:
        """Fetch a judgment detail page and extract full text."""
        slug = entry["slug"]
        if not slug.startswith("http"):
            url = BASE_URL + "/" + slug.lstrip("/")
        else:
            url = slug

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch detail page {url}: {e}")
            return None

        text = self._extract_text(resp.text)
        if not text:
            return None

        date_iso = parse_date(entry["date_raw"])
        case_id = slug.rstrip("/").split("/")[-1]

        return {
            "_id": case_id,
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": entry["title"],
            "text": text,
            "date": date_iso,
            "court": entry["court"],
            "judge": entry["judge"],
            "url": url,
            "pdf_url": entry.get("pdf_url"),
        }

    def _extract_text(self, page_html: str) -> Optional[str]:
        """Extract judgment text from <section class='pdf-content'>."""
        # Find the pdf-content section
        start_marker = 'class="pdf-content"'
        end_marker = '</section>'

        start_idx = page_html.find(start_marker)
        if start_idx == -1:
            return None

        # Find the closing </section> after pdf-content
        end_idx = page_html.find(end_marker, start_idx)
        if end_idx == -1:
            end_idx = len(page_html)

        content_html = page_html[start_idx:end_idx]
        text = strip_html(content_html)

        # Remove the leading class attribute text
        if text.startswith('pdf-content'):
            text = text[len('pdf-content'):].strip()

        return text if len(text) >= 200 else None


def main():
    scraper = BarbadosJudiciaryScraper()
    args = sys.argv[1:]

    if not args:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample]")
        sys.exit(1)

    command = args[0]
    sample = "--sample" in args

    if command == "test":
        try:
            resp = scraper.session.get(BASE_URL + "/judgments/", timeout=15)
            print(f"Connection test: HTTP {resp.status_code}")
            if resp.status_code == 200:
                print("OK: Site is accessible")
                sys.exit(0)
            else:
                print("WARN: Unexpected status code")
                sys.exit(1)
        except Exception as e:
            print(f"FAIL: {e}")
            sys.exit(1)

    if command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).resolve().parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            fname = sample_dir / f"{record['_id'][:80]}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"BB/JudiciaryDecisions: {count} records saved to sample/")
        print(f"{'='*60}")

        if count == 0:
            logger.error("No records fetched!")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
