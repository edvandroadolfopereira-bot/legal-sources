#!/usr/bin/env python3
"""
PL/MonitorPolski -- Monitor Polski (Polish Official Gazette) Data Fetcher

Fetches official acts published in Monitor Polski (Dziennik Urzędowy
Rzeczypospolitej Polskiej "Monitor Polski"), Poland's second official journal.
Unlike Dziennik Ustaw (universally binding legislation, covered by
PL/DziennikUrzedowy), Monitor Polski publishes government instruments such as
resolutions of the Council of Ministers (uchwały), orders (zarządzenia),
official announcements (obwieszczenia), and resolutions of the Sejm/Senate —
i.e. official state-authored content that is not generally-applicable statute
law. We therefore classify it as `doctrine`.

Strategy:
  - List acts by year: GET /eli/acts/MP/{year} returns JSON with all acts
  - Get act metadata: GET /eli/acts/MP/{year}/{pos} returns detailed metadata
  - Get full text: GET /eli/acts/MP/{year}/{pos}/text.pdf (MP acts are PDF-only)
    -> extracted to plain text with PyMuPDF (fitz)

API Documentation:
  - Base URL: https://api.sejm.gov.pl
  - ELI endpoint: /eli/acts/MP/{year}/{position}
  - Full text PDF: /eli/acts/MP/{year}/{position}/text.pdf
  - Publisher code: MP (Monitor Polski)

Usage:
  python bootstrap.py bootstrap           # Full initial pull
  python bootstrap.py bootstrap-fast      # Alias for bootstrap (VPS runner)
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py update              # Incremental update (recent acts)
  python bootstrap.py test-api            # Quick API connectivity test
"""

import sys
import io
import json
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PL.MonitorPolski")

# API configuration
BASE_URL = "https://api.sejm.gov.pl"
PUBLISHER = "MP"

# Years to scrape (most recent first; Monitor Polski digital coverage is strong
# from ~2001 onwards, with consistent PDF text for all acts).
YEARS_TO_SCRAPE = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]


class MonitorPolskiScraper(BaseScraper):
    """
    Scraper for PL/MonitorPolski -- Monitor Polski official gazette.
    Country: PL
    URL: https://monitorpolski.gov.pl

    Data types: doctrine
    Auth: none (Open Government Data)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json,application/pdf,*/*;q=0.8",
            "Accept-Language": "pl,en;q=0.9",
        })

    def _api_get(self, endpoint: str, timeout: int = 60) -> Optional[dict]:
        """Make GET request to a JSON API endpoint."""
        url = f"{BASE_URL}{endpoint}"
        try:
            self.rate_limiter.wait()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.JSONDecodeError:
            return None
        except Exception as e:
            logger.warning(f"API request failed for {endpoint}: {e}")
            return None

    def _api_get_bytes(self, endpoint: str, timeout: int = 90) -> bytes:
        """Make GET request and return raw bytes (PDF)."""
        url = f"{BASE_URL}{endpoint}"
        try:
            self.rate_limiter.wait()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning(f"PDF request failed for {endpoint}: {e}")
            return b""

    def _list_acts_by_year(self, year: int) -> List[Dict[str, Any]]:
        """List all acts for a given year."""
        endpoint = f"/eli/acts/{PUBLISHER}/{year}"
        data = self._api_get(endpoint)
        if data and "items" in data:
            logger.info(f"Found {data.get('count', len(data['items']))} MP acts for {year}")
            return data["items"]
        return []

    def _get_act_details(self, year: int, pos: int) -> Optional[Dict[str, Any]]:
        """Get detailed metadata for a specific act."""
        endpoint = f"/eli/acts/{PUBLISHER}/{year}/{pos}"
        return self._api_get(endpoint)

    @staticmethod
    def _clean_pdf_text(text: str) -> str:
        """Clean extracted PDF text: normalize whitespace, drop hyphenation."""
        # De-hyphenate words split across line breaks
        text = re.sub(r"-\n(\w)", r"\1", text)
        # Collapse runs of spaces/tabs
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse 3+ newlines to a paragraph break
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip trailing spaces on each line
        text = "\n".join(line.rstrip() for line in text.splitlines())
        return text.strip()

    def _get_full_text(self, year: int, pos: int) -> str:
        """
        Fetch the act PDF and extract plain text with PyMuPDF.

        Monitor Polski acts are published as PDF only (textHTML=false), so we
        download /text.pdf and extract the body text.
        """
        endpoint = f"/eli/acts/{PUBLISHER}/{year}/{pos}/text.pdf"
        pdf_bytes = self._api_get_bytes(endpoint)
        if not pdf_bytes:
            return ""

        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF (fitz) is required for PDF text extraction")
            return ""

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            parts = [page.get_text() for page in doc]
            doc.close()
        except Exception as e:
            logger.warning(f"PDF extraction failed for {year}/{pos}: {e}")
            return ""

        return self._clean_pdf_text("\n".join(parts))

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all Monitor Polski acts with extracted full text."""
        logger.info("Starting full Monitor Polski fetch...")

        for year in YEARS_TO_SCRAPE:
            logger.info(f"Fetching MP acts from {year}...")
            acts = self._list_acts_by_year(year)

            for act in acts:
                pos = act.get("pos")
                if not pos:
                    continue

                details = self._get_act_details(year, pos)
                if details:
                    act.update(details)

                full_text = self._get_full_text(year, pos)
                if full_text and len(full_text) > 200:
                    act["full_text"] = full_text
                    yield act
                else:
                    logger.warning(f"No usable text for MP {year}/{pos}, skipping")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield acts changed since the given date (recent years only)."""
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        current_year = datetime.now().year

        for year in [current_year, current_year - 1]:
            logger.info(f"Checking MP {year} for updates since {since_str}...")
            acts = self._list_acts_by_year(year)

            for act in acts:
                change_date = act.get("changeDate", "")
                if change_date and change_date >= since_str:
                    pos = act.get("pos")
                    if not pos:
                        continue
                    details = self._get_act_details(year, pos)
                    if details:
                        act.update(details)
                    full_text = self._get_full_text(year, pos)
                    if full_text:
                        act["full_text"] = full_text
                    yield act

    def normalize(self, raw: dict) -> dict:
        """Transform raw API data into the standard schema (with full text)."""
        eli = raw.get("ELI", "")
        year = raw.get("year", 0)
        pos = raw.get("pos", 0)

        doc_id = eli if eli else f"MP/{year}/{pos}"

        promulgation = raw.get("promulgation", "")
        announcement = raw.get("announcementDate", "")
        date = promulgation or announcement

        # Public-facing detail page on the official gazette portal
        url = f"https://monitorpolski.gov.pl/MP/{year}/{pos}"

        full_text = raw.get("full_text", "")

        return {
            # Required base fields
            "_id": doc_id,
            "_source": "PL/MonitorPolski",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            # Standard fields
            "title": raw.get("title", ""),
            "text": full_text,  # MANDATORY FULL TEXT
            "date": date,
            "url": url,
            # Source-specific fields
            "eli": eli,
            "address": raw.get("address", ""),
            "display_address": raw.get("displayAddress", ""),
            "year": year,
            "pos": pos,
            "doc_type": raw.get("type", ""),
            "status": raw.get("status", ""),
            "in_force": raw.get("inForce", ""),
            "entry_into_force": raw.get("entryIntoForce", ""),
            "keywords": raw.get("keywords", []),
            "released_by": raw.get("releasedBy", []),
            "references": raw.get("references", {}),
            "language": "pl",
        }

    def test_api(self):
        """Quick connectivity and API test."""
        print("Testing Monitor Polski ELI API...")

        print("\n1. Testing year listing endpoint...")
        acts = self._list_acts_by_year(2024)
        if acts:
            print(f"   Found {len(acts)} MP acts for 2024")
            print(f"   First act: {acts[0].get('title', '')[:60]}...")
        else:
            print("   ERROR: No acts returned")
            return

        print("\n2. Testing full text (PDF) extraction...")
        first_pos = acts[0].get("pos")
        text = self._get_full_text(2024, first_pos)
        if text:
            print(f"   Text length: {len(text)} characters")
            print(f"   Preview: {text[:200]}...")
        else:
            print("   WARNING: Could not extract full text")

        print("\nAPI test complete!")


def main():
    scraper = MonitorPolskiScraper()

    if len(sys.argv) < 2:
        print(
            "Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test-api] "
            "[--sample] [--sample-size N]"
        )
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 12
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command == "test-api":
        scraper.test_api()

    elif command in ("bootstrap", "bootstrap-fast"):
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
            print(
                f"\nSample complete: "
                f"{stats.get('sample_records_saved', 0)} records saved to sample/"
            )
        else:
            stats = scraper.bootstrap()
            print(
                f"\nBootstrap complete: {stats['records_new']} new, "
                f"{stats['records_updated']} updated, "
                f"{stats['records_skipped']} skipped"
            )
        print(json.dumps(stats, indent=2))

    elif command == "update":
        stats = scraper.update()
        print(
            f"\nUpdate complete: {stats['records_new']} new, "
            f"{stats['records_updated']} updated"
        )
        print(json.dumps(stats, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
