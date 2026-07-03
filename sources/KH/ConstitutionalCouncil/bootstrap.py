#!/usr/bin/env python3
"""
KH/ConstitutionalCouncil -- Constitutional Council of Cambodia Decisions

Fetches decisions of Cambodia's Constitutional Council from ccc.gov.kh.
~108 decisions available in English (2003-2020) as PDF files.

Access pattern:
  1. Listing pages per year: decision_en.php?postyear=YYYY
  2. Detail pages: detail_info_en.php?_txtID=NNN
  3. PDF download: datapublic/subdata/{filename}.pdf

Usage:
  python bootstrap.py bootstrap --sample          # Sample records
  python bootstrap.py bootstrap --sample --count 15
  python bootstrap.py bootstrap                   # Full bootstrap
  python bootstrap.py bootstrap-fast              # Alias for bootstrap
  python bootstrap.py test-api                    # Connectivity check
"""

import io
import re
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.KH.ConstitutionalCouncil")

BASE_URL = "https://www.ccc.gov.kh"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

YEARS = list(range(2003, 2026))
MIN_TEXT_CHARS = 200

_DECISION_NO_RE = re.compile(r"Decision\s+N[ºo°]\s*([\d/]+)")
_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_TITLE_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.DOTALL)
_TITLE_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})"
)
_MONTH_MAP = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2, falling back to pdfminer."""
    if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
        return ""
    text = ""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(
            (page.extract_text() or "") for page in reader.pages
        )
    except Exception as e:
        logger.debug(f"PyPDF2 failed: {e}")
    if len(text.strip()) < MIN_TEXT_CHARS:
        try:
            from pdfminer.high_level import extract_text as pm_extract
            alt = pm_extract(io.BytesIO(pdf_bytes)) or ""
            if len(alt.strip()) > len(text.strip()):
                text = alt
        except Exception as e:
            logger.debug(f"pdfminer failed: {e}")
    return _clean_text(text)


def _clean_text(text: str) -> str:
    """Collapse whitespace while preserving paragraph breaks."""
    if not text:
        return ""
    text = text.replace("\x0c", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class ConstitutionalCouncilScraper(BaseScraper):
    """Scraper for KH/ConstitutionalCouncil — Cambodia constitutional decisions."""

    def __init__(self):
        super().__init__(Path(__file__).parent)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def _get_decision_ids(self) -> list:
        """Get all decision txtIDs from listing pages, oldest first."""
        all_ids = []
        for year in YEARS:
            url = f"{BASE_URL}/decision_en.php?postyear={year}&postyear1=YEAR%20{year}"
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"Failed to fetch year {year}: {e}")
                continue

            html = resp.text
            pattern = f"DECISION YEAR {year}</div>\\s*<div class=\"middleparagraph[^\"]*\">(.*?)</div>"
            match = re.search(pattern, html, re.DOTALL)
            if match:
                content = match.group(1)
                ids = list(dict.fromkeys(
                    re.findall(r"detail_info_en\.php\?_txtID=(\d+)", content)
                ))
                all_ids.extend([(year, tid) for tid in ids])
                if ids:
                    logger.info(f"  {year}: {len(ids)} decisions")
            time.sleep(0.5)

        logger.info(f"Total decisions found: {len(all_ids)}")
        return all_ids

    def _fetch_decision(self, year: int, txt_id: str) -> Optional[dict]:
        """Fetch a single decision detail page and its PDF."""
        detail_url = f"{BASE_URL}/detail_info_en.php?_txtID={txt_id}"
        try:
            resp = self.session.get(detail_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"  txtID {txt_id}: detail page failed ({e})")
            return None

        html = resp.text

        # Extract title
        title_match = _TITLE_RE.search(html)
        title = ""
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

        # Extract date from title (unambiguous English format) first
        date_str = None
        title_date_match = _TITLE_DATE_RE.search(title)
        if title_date_match:
            month_name, day, yr = title_date_match.groups()
            mm = _MONTH_MAP[month_name]
            date_str = f"{yr}-{mm}-{day.zfill(2)}"
        else:
            # Fallback: parse from datetimes span (DD/MM/YYYY on this site)
            date_match = re.search(r'class="datetimes">([\d/]+)</span>', html)
            if date_match:
                raw_date = date_match.group(1)
                dm = _DATE_RE.match(raw_date)
                if dm:
                    a, b, yr = dm.group(1), dm.group(2), dm.group(3)
                    # If first value > 12, it must be DD/MM/YYYY
                    if int(a) > 12:
                        date_str = f"{yr}-{b}-{a}"
                    elif int(b) > 12:
                        date_str = f"{yr}-{a}-{b}"
                    else:
                        # Ambiguous — trust title parsing above
                        date_str = f"{yr}-{b}-{a}"

        # Extract summary
        summary = ""
        p_match = re.search(r"<p>(.*?)</p>", html, re.DOTALL)
        if p_match:
            summary = re.sub(r"<[^>]+>", "", p_match.group(1)).strip()

        # Extract PDF link
        pdf_match = re.search(r'href="([^"]*\.pdf)"', html)
        if not pdf_match:
            logger.debug(f"  txtID {txt_id}: no PDF link found")
            return None

        pdf_path = pdf_match.group(1)
        if pdf_path.startswith("http"):
            pdf_url = pdf_path
        else:
            pdf_url = f"{BASE_URL}/{pdf_path}"

        # Download PDF
        time.sleep(1)
        try:
            pdf_resp = self.session.get(pdf_url, timeout=60)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
        except Exception as e:
            logger.warning(f"  txtID {txt_id}: PDF download failed ({e})")
            return None

        # Extract text
        text = _extract_pdf_text(pdf_bytes)
        if len(text) < MIN_TEXT_CHARS:
            logger.debug(f"  txtID {txt_id}: insufficient text ({len(text)} chars)")
            return None

        # Extract decision number
        decision_id = ""
        dec_match = _DECISION_NO_RE.search(title) or _DECISION_NO_RE.search(text[:500])
        if dec_match:
            decision_id = dec_match.group(1).strip()
        else:
            decision_id = f"CCC-{txt_id}"

        return {
            "txt_id": txt_id,
            "year": year,
            "title": title,
            "date": date_str,
            "summary": summary,
            "text": text,
            "decision_id": decision_id,
            "detail_url": detail_url,
            "pdf_url": pdf_url,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions with full text."""
        decision_ids = self._get_decision_ids()
        for year, txt_id in decision_ids:
            record = self._fetch_decision(year, txt_id)
            if record:
                yield record
            time.sleep(1)

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield decisions from recent years only."""
        since_year = since.year
        decision_ids = self._get_decision_ids()
        for year, txt_id in decision_ids:
            if year >= since_year:
                record = self._fetch_decision(year, txt_id)
                if record:
                    yield record
                time.sleep(1)

    def normalize(self, raw: dict) -> dict:
        """Transform raw decision into standard schema."""
        return {
            "_id": f"KH-CC-{raw['txt_id']}",
            "_source": "KH/ConstitutionalCouncil",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date"),
            "decision_id": raw["decision_id"],
            "summary": raw.get("summary", ""),
            "url": raw["detail_url"],
            "pdf_url": raw["pdf_url"],
            "year": raw["year"],
        }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="KH/ConstitutionalCouncil scraper")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Full or sample bootstrap")
    boot.add_argument("--sample", action="store_true")
    boot.add_argument("--count", type=int, default=15)

    boot_fast = sub.add_parser("bootstrap-fast", help="Alias for bootstrap")
    boot_fast.add_argument("--sample", action="store_true")
    boot_fast.add_argument("--count", type=int, default=15)

    sub.add_parser("test-api", help="Test connectivity")
    sub.add_parser("update", help="Incremental update")

    args = parser.parse_args()

    scraper = ConstitutionalCouncilScraper()

    if args.command in ("bootstrap", "bootstrap-fast"):
        stats = scraper.bootstrap(
            sample_mode=args.sample,
            sample_size=args.count,
        )
        logger.info(f"Bootstrap complete: {stats}")
    elif args.command == "test-api":
        resp = scraper.session.get(
            f"{BASE_URL}/decision_en.php?postyear=2007&postyear1=YEAR%202007",
            timeout=15,
        )
        if "DECISION YEAR 2007" in resp.text:
            print("OK: ccc.gov.kh is accessible and returns decision listings")
        else:
            print("FAIL: Could not retrieve decision listings")
            sys.exit(1)
    elif args.command == "update":
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=365)
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update complete: {stats}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
