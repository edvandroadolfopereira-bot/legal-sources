#!/usr/bin/env python3
"""
MT/MCCAA -- Malta Competition and Consumer Affairs Authority — Competition Decisions

Fetches competition decisions (concentration/merger clearances and antitrust
enforcement) from the Office for Competition within the MCCAA.

Strategy:
  - Scrapes the HTML table at /decisions/ for concentration decisions
  - Scrapes /antitrust-decisions/ for antitrust enforcement decisions
  - Each row has data-title, data-link attributes containing case info and PDF URL
  - Downloads PDFs and extracts full text via pdfplumber/pypdf

Endpoints:
  - Concentrations: https://mccaa.org.mt/decisions/
  - Antitrust: https://mccaa.org.mt/antitrust-decisions/

Data:
  - ~133 concentration/merger decisions (2011-2026)
  - ~9 antitrust decisions (2015-2021)
  - Full text from PDF documents

License: Public regulatory data (Malta)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records for validation
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import re
import html
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.MT.MCCAA")

BASE_URL = "https://mccaa.org.mt"

# Pages containing decision tables
DECISIONS_PAGES = [
    ("/decisions/", "concentration"),
    ("/antitrust-decisions/", "antitrust"),
]

# Date format used on the site: "30 April 2026", "01 February 2021"
DATE_PATTERN = re.compile(r"(\d{1,2}\s+\w+\s+\d{4})")


class MCCAAScraper(BaseScraper):
    """
    Scraper for MT/MCCAA -- Malta Competition Authority Decisions.
    Country: MT
    URL: https://mccaa.org.mt

    Data types: case_law
    Auth: none (public regulatory data)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=60,
        )

    def _parse_decisions_page(self, path: str, decision_type: str) -> list:
        """Parse a decisions page and return list of decision metadata dicts."""
        self.rate_limiter.wait()
        resp = self.client.get(path)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch {path}: HTTP {resp.status_code}")
            return []

        page_html = resp.text
        decisions = []

        # Each decision is in a <tr> with data-title and data-link attributes
        # Pattern: data-title="..." data-link="..."
        row_pattern = re.compile(
            r'data-title="([^"]*)"[^>]*data-link="([^"]*)"',
            re.DOTALL
        )

        # Find all rows with data-title and data-link
        rows = row_pattern.findall(page_html)

        # Also extract dates and full titles from the table cells
        # Pattern: <span class="title-text">DATE</span> ... <span class="title-text">TITLE</span> ... <span class="title-text">SECTOR</span>
        # We'll parse the full HTML around each row for more detail

        # Split HTML by table rows to get context for each decision
        row_blocks = re.split(r'<tr[^>]*\s+data-title=', page_html)

        for i, block in enumerate(row_blocks[1:], 1):  # skip first split (before first row)
            # Extract data-title and data-link from the opening tag
            title_match = re.search(r'^"([^"]*)"', block)
            link_match = re.search(r'data-link="([^"]*)"', block)

            if not title_match or not link_match:
                continue

            raw_title = html.unescape(title_match.group(1)).strip()
            pdf_url = link_match.group(1).strip()

            # Extract all title-text spans (date, title, sector)
            spans = re.findall(r'<span class="title-text">([^<]*)</span>', block)

            date_str = ""
            full_title = raw_title
            sector = ""

            if len(spans) >= 1:
                date_str = spans[0].strip()
            if len(spans) >= 2:
                full_title = html.unescape(spans[1].strip()) or raw_title
            if len(spans) >= 3:
                sector = spans[2].strip()

            # Parse date
            date_iso = self._parse_date(date_str)

            # Extract case reference from title (e.g., COMP-MCCAA/09/2026)
            case_ref_match = re.match(r'(COMP[-/]MCCAA/\d+/\d{4})', full_title, re.IGNORECASE)
            case_reference = case_ref_match.group(1) if case_ref_match else ""

            decisions.append({
                "title": full_title,
                "case_reference": case_reference,
                "date": date_iso,
                "date_raw": date_str,
                "sector": sector,
                "pdf_url": pdf_url,
                "decision_type": decision_type,
            })

        logger.info(f"Found {len(decisions)} {decision_type} decisions on {path}")
        return decisions

    def _parse_date(self, date_str: str) -> str:
        """Parse date string like '30 April 2026' to ISO format."""
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str.strip(), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try other formats
            for fmt in ["%d %b %Y", "%B %d, %Y", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return ""

    def _make_id(self, decision: dict) -> str:
        """Create a stable unique ID for a decision."""
        # Use PDF filename as the primary ID — it's always unique
        pdf_name = decision["pdf_url"].split("/")[-1].replace(".pdf", "")
        return pdf_name

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all competition decisions with full text from PDFs."""
        all_decisions = []
        for path, decision_type in DECISIONS_PAGES:
            decisions = self._parse_decisions_page(path, decision_type)
            all_decisions.extend(decisions)

        logger.info(f"Total decisions found: {len(all_decisions)}")

        for decision in all_decisions:
            doc_id = self._make_id(decision)

            # Download and extract PDF text
            self.rate_limiter.wait()
            text = extract_pdf_markdown(
                source="MT/MCCAA",
                source_id=doc_id,
                pdf_url=decision["pdf_url"],
                table="case_law",
            )

            if not text or len(text.strip()) < 50:
                logger.debug(f"Skipping {doc_id} — no extractable text from PDF")
                continue

            yield self.normalize({**decision, "text": text, "_id": doc_id})

    def fetch_updates(self, since: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """Fetch decisions updated since a given date."""
        # For this source, just re-fetch all and let dedup handle it
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw decision data into standard schema."""
        return {
            "_id": raw["_id"],
            "_source": "MT/MCCAA",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date", ""),
            "url": raw.get("pdf_url", ""),
            "case_reference": raw.get("case_reference", ""),
            "sector": raw.get("sector", ""),
            "decision_type": raw.get("decision_type", ""),
            "language": "en",
        }

    def test_connection(self) -> bool:
        """Test connectivity to the MCCAA website."""
        try:
            resp = self.client.get("/decisions/")
            return resp.status_code == 200
        except Exception:
            return False


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="MT/MCCAA Competition Decisions Scraper")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Only fetch a sample of records (for validation)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch all records (default for bootstrap)",
    )

    args = parser.parse_args()
    scraper = MCCAAScraper()

    if args.command == "test":
        if scraper.test_connection():
            print("OK — Connection successful")
            sys.exit(0)
        else:
            print("FAIL — Could not connect")
            sys.exit(1)

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else 999999

        for record in scraper.fetch_all():
            count += 1
            # Save sample
            fname = re.sub(r'[^\w\-]', '_', record["_id"])[:80]
            sample_path = sample_dir / f"{fname}.json"
            with open(sample_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            text_len = len(record.get("text", ""))
            logger.info(f"[{count}] {record['_id']} — {text_len} chars")

            if count >= max_records:
                break

        print(f"\nDone: {count} records saved to {sample_dir}")
        return

    if args.command == "update":
        count = 0
        for record in scraper.fetch_updates():
            count += 1
            logger.info(f"[{count}] {record['_id']}")
        print(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
