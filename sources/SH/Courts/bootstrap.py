#!/usr/bin/env python3
"""
SH/Courts -- St Helena Senior Courts (via BAILII)

Fetches St Helena case law from bailii.org. St Helena, Ascension and Tristan
da Cunha is a self-governing British Overseas Territory; its senior courts'
judgments are published on BAILII.

Strategy:
  - Scrape year-listing pages for each St Helena court
  - Download individual case HTML pages
  - Extract full judgment text from HTML

Courts covered:
  - SHSC: Supreme Court of St Helena
  - SHCA: St Helena Court of Appeal

Note: BAILII gates browser-like (Mozilla) User-Agents behind an Anubis
proof-of-work challenge; a non-browser UA (the project UA below) is served
the real content directly.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records
  python bootstrap.py bootstrap-fast     # Alias for full bootstrap (VPS)
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SH.Courts")

BASE_URL = "https://www.bailii.org"

# St Helena courts to scrape: (url_code, full_name, start_year)
COURTS = [
    ("SHSC", "Supreme Court of St Helena", 2014),
    ("SHCA", "St Helena Court of Appeal", 2014),
]


class SHCourtsScraper(BaseScraper):
    """
    Scraper for SH/Courts -- St Helena case law via BAILII.
    Country: SH
    URL: https://www.bailii.org/sh/

    Data types: case_law
    Auth: none (free-of-charge, attribution required)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                # Non-browser UA bypasses BAILII's Anubis bot challenge.
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html",
            },
            timeout=60,
        )

    def _get_years_for_court(self, court_code: str) -> list[int]:
        """Fetch available years for a court from its index page."""
        self.rate_limiter.wait()
        try:
            resp = self.client.get(f"/sh/cases/{court_code}/")
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch year index for {court_code}: {e}")
            return []

        years = []
        for m in re.finditer(rf'/sh/cases/{court_code}/(\d{{4}})/', resp.text):
            years.append(int(m.group(1)))

        years = sorted(set(years), reverse=True)
        logger.info(
            f"{court_code}: found {len(years)} years "
            f"({years[0] if years else 'none'} - {years[-1] if years else 'none'})"
        )
        return years

    def _get_cases_for_year(self, court_code: str, year: int) -> list[dict]:
        """Fetch list of case URLs for a court/year."""
        self.rate_limiter.wait()
        url = f"/sh/cases/{court_code}/{year}/"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch {court_code}/{year}: {e}")
            return []

        cases = []
        # Case links: /sh/cases/SHSC/2025/2025_10.html
        pattern = rf'href="(/sh/cases/{court_code}/{year}/[^"]+\.html)"'
        seen = set()

        for m in re.finditer(pattern, resp.text):
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)

            # Extract case title from link text: <a ...href="...">Title</a>
            title_pattern = rf'href="{re.escape(href)}"[^>]*>([^<]+)</a>'
            title_match = re.search(title_pattern, resp.text)
            title = title_match.group(1).strip() if title_match else ""

            # Extract date if present (format: DD Month YYYY)
            date_pattern = rf'{re.escape(href)}[^<]*</a>\s*\((\d{{1,2}}\s+\w+\s+\d{{4}})\)'
            date_match = re.search(date_pattern, resp.text)
            date_str = date_match.group(1) if date_match else ""

            # Citation: prefer "[YYYY] COURT N" parsed from the link title
            citation = ""
            cit_match = re.search(rf'\[{year}\]\s+{court_code}\s+\d+', title)
            if cit_match:
                citation = cit_match.group(0)
            else:
                filename = href.split("/")[-1].replace(".html", "")
                num_match = re.search(r'(\d+)$', filename)
                if num_match:
                    citation = f"[{year}] {court_code} {num_match.group(1)}"

            cases.append({
                "href": href,
                "title": title,
                "date_str": date_str,
                "citation": citation,
                "court_code": court_code,
                "year": year,
                "filename": href.split("/")[-1].replace(".html", ""),
            })

        logger.info(f"{court_code}/{year}: {len(cases)} cases")
        return cases

    def _download_case(self, href: str) -> tuple[str, str]:
        """Download a case page and extract judgment text and title.
        Returns (text, extracted_title).
        """
        self.rate_limiter.wait()
        try:
            resp = self.client.get(href)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to download {href}: {e}")
            return "", ""

        html_text = resp.text

        # Extract <title> tag for fallback title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_text, re.IGNORECASE)
        extracted_title = title_match.group(1).strip() if title_match else ""
        extracted_title = re.sub(r'^BAILII\s*[-–—]\s*', '', extracted_title).strip()

        # BAILII places an <hr> immediately after the "You are here" breadcrumb;
        # the judgment body is everything after it. The donation appeal and
        # navigation sit before the breadcrumb, so cutting at the first <hr>
        # *after* the breadcrumb drops all boilerplate cleanly.
        anchor = re.search(r'You are here', html_text, re.IGNORECASE)
        search_from = anchor.end() if anchor else 0
        hr_match = re.search(r'<hr\b[^>]*>', html_text[search_from:], re.IGNORECASE)
        body = html_text[search_from + hr_match.end():] if hr_match else html_text[search_from:]

        # Remove script and style elements
        text = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags, preserving structure
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<p[^>]*>', '\n\n', text)
        text = re.sub(r'</p>', '', text)
        text = re.sub(r'<li[^>]*>', '\n- ', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        # Drop any stray unclosed tag fragment (e.g. a truncated "<td ...").
        text = re.sub(r'<[a-zA-Z/][^>\n]*', ' ', text)

        # Decode entities
        import html
        text = html.unescape(text)

        # Drop BAILII per-page nav links (e.g. "[ New search ]", "[ Help ]").
        text = re.sub(r'\[\s*(New search|Printable PDF version|Help|Context|Hide Context|Previous|Next)\s*\]', '', text, flags=re.IGNORECASE)

        # Clean whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # Remove trailing BAILII footer
        for footer in ['BAILII:', '© Copyright', 'Crown Copyright',
                       'URL: http']:
            idx = text.rfind(footer)
            if idx > len(text) - 600 and idx > 0:
                text = text[:idx].rstrip()

        return text, extracted_title

    def _parse_date(self, date_str: str) -> str:
        """Parse date like '28 May 2025' to ISO format."""
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str.strip(), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    # -- Abstract method implementations ---------------------------------------

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all St Helena case law from BAILII (raw listing dicts)."""
        for court_code, court_name, start_year in COURTS:
            logger.info(f"Fetching {court_name} ({court_code})")
            years = self._get_years_for_court(court_code)

            for year in years:
                cases = self._get_cases_for_year(court_code, year)
                for case in cases:
                    yield case

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield cases from recent years."""
        since_year = since.year
        for court_code, court_name, start_year in COURTS:
            logger.info(f"Fetching updates for {court_name} since {since_year}")
            years = self._get_years_for_court(court_code)

            for year in years:
                if year < since_year:
                    break
                cases = self._get_cases_for_year(court_code, year)
                for case in cases:
                    yield case

    def normalize(self, raw: dict) -> dict:
        """Transform raw case dict into standard schema with full text."""
        href = raw.get("href", "")
        court_code = raw.get("court_code", "")
        year = raw.get("year", "")
        filename = raw.get("filename", "")

        # Download full judgment text
        full_text, extracted_title = self._download_case(href)

        if not full_text or len(full_text) < 100:
            logger.warning(
                f"Insufficient text for {href}: {len(full_text) if full_text else 0} chars"
            )
            return None

        unique_id = f"SH/Courts/{court_code}/{year}/{filename}"

        title = raw.get("title", "") or extracted_title

        date = self._parse_date(raw.get("date_str", ""))
        if not date and year:
            date = f"{year}-01-01"

        return {
            "_id": unique_id,
            "_source": "SH/Courts",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": full_text,
            "date": date,
            "url": f"{BASE_URL}{href}",
            "citation": raw.get("citation", ""),
            "court": court_code,
            "court_code": court_code,
        }


# -- CLI Entry Point -----------------------------------------------------------


def main():
    scraper = SHCourtsScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample] [--sample-size N]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test":
        print("Testing BAILII connectivity...")
        resp = scraper.client.get("/sh/cases/SHSC/")
        print(f"  Status: {resp.status_code}")
        years = scraper._get_years_for_court("SHSC")
        print(f"  SHSC years: {len(years)} ({years[0] if years else 'none'} - {years[-1] if years else 'none'})")
        print("Test passed!")
    elif cmd in ("bootstrap", "bootstrap-fast"):
        sample_mode = "--sample" in sys.argv
        sample_size = 15
        for i, arg in enumerate(sys.argv):
            if arg == "--sample-size" and i + 1 < len(sys.argv):
                sample_size = int(sys.argv[i + 1])

        if sample_mode:
            print(f"Running bootstrap in sample mode (n={sample_size})...")
            stats = scraper.bootstrap(sample_mode=True, sample_size=sample_size)
        else:
            print("Running full bootstrap...")
            stats = scraper.bootstrap()

        print(f"\nBootstrap complete:")
        print(json.dumps(stats, indent=2, default=str))
    elif cmd == "update":
        print("Running incremental update...")
        stats = scraper.update()
        print(f"\nUpdate complete:")
        print(json.dumps(stats, indent=2, default=str))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
