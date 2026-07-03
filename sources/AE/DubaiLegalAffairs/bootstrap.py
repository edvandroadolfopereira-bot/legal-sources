#!/usr/bin/env python3
"""
AE/DubaiLegalAffairs -- Dubai Official Gazette via Legal Affairs Department

Downloads gazette PDFs from legal.dubai.gov.ae and extracts text with pdfplumber.
Each gazette issue becomes one record with the full text of all legislation it contains.

Usage:
  python bootstrap.py bootstrap --sample    # Fetch 15 sample records
  python bootstrap.py bootstrap             # Full bootstrap
  python bootstrap.py test                  # Quick connectivity test
"""

import io
import json
import os
import re
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Dict, Tuple
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AE.DubaiLegalAffairs")

BASE_URL = "https://legal.dubai.gov.ae"
GAZETTE_PAGE = f"{BASE_URL}/en/Services/Pages/Official-Gazette.aspx"
DDL_NAME = "ctl00$ctl82$g_2cb19bc1_b4d0_42e3_8484_d28431570be2$ctl00$ddlyear"
DELAY = 2.0
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SOURCE_DIR = Path(__file__).resolve().parent
DATA_DIR = SOURCE_DIR / "data"
SAMPLE_DIR = SOURCE_DIR / "sample"
SOURCE_ID = "AE/DubaiLegalAffairs"


def _parse_date(date_str: str) -> Optional[str]:
    """Parse date from DD/MM/YYYY or M/D/YYYY format to ISO 8601."""
    for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_hidden_fields(html: str) -> Dict[str, str]:
    """Extract all ASP.NET hidden form fields from HTML."""
    fields = {}
    for m in re.finditer(
        r'<input type="hidden" name="([^"]*)"[^>]*value="([^"]*)"', html
    ):
        fields[m.group(1)] = m.group(2)
    return fields


def _parse_gazette_items(html: str) -> List[Dict[str, str]]:
    """Parse gazette items from page HTML. Returns list of {issue, date, url}."""
    items = []
    # Match rows: <td>Issue No. 769</td><td>5/5/2026</td>...<a href="/OfficialGazette/...pdf"
    pattern = re.compile(
        r'<td>Issue No\.\s*(\d+)</td>'
        r'<td>(\d+/\d+/\d+)</td>'
        r'.*?'
        r'href="(/OfficialGazette/[^"]+\.pdf)"',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        issue_num = int(m.group(1))
        date_str = m.group(2)
        pdf_path = unquote(m.group(3))
        items.append({
            "issue": issue_num,
            "date": date_str,
            "pdf_url": f"{BASE_URL}{pdf_path}",
        })
    return items


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return ""

    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"PDF extraction error: {e}")
        return ""

    return "\n\n".join(text_parts)


class DubaiLegalAffairsScraper(BaseScraper):
    """Scraper for Dubai Official Gazette PDFs."""

    def __init__(self):
        # Initialize BaseScraper (loads config, sets source_dir/storage/status).
        # Without this the generic VPS runner crashes accessing self.config
        # (see issue #863).
        super().__init__()
        self.http = HttpClient(
            headers={"User-Agent": UA},
            timeout=60,
        )
        self._session = None

    def _get_session(self):
        """Get or create a requests session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": UA})
        return self._session

    def _get_gazette_items_for_year(
        self, year: int, hidden_fields: Dict[str, str]
    ) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
        """Fetch gazette items for a specific year via ASP.NET PostBack."""
        session = self._get_session()

        data = dict(hidden_fields)
        data["__EVENTTARGET"] = DDL_NAME
        data["__EVENTARGUMENT"] = ""
        data[DDL_NAME] = str(year)

        resp = session.post(GAZETTE_PAGE, data=data, timeout=30)
        resp.raise_for_status()
        html = resp.text

        items = _parse_gazette_items(html)
        new_fields = _extract_hidden_fields(html)

        return items, new_fields

    def _get_all_gazette_items(
        self, years: Optional[List[int]] = None
    ) -> Generator[Dict[str, str], None, None]:
        """Iterate gazette items across all years."""
        session = self._get_session()

        # Get initial page (loads 2026 by default)
        resp = session.get(GAZETTE_PAGE, timeout=30)
        resp.raise_for_status()
        html = resp.text

        hidden_fields = _extract_hidden_fields(html)
        default_items = _parse_gazette_items(html)

        if years is None:
            # Extract available years from dropdown
            years = sorted(
                [int(m) for m in re.findall(r'value="(\d{4})"', html)],
                reverse=True,
            )

        # Yield default year items (2026)
        if years and years[0] == 2026:
            for item in default_items:
                yield item
            years = years[1:]
            time.sleep(DELAY)

        # PostBack for each remaining year
        for year in years:
            try:
                items, hidden_fields = self._get_gazette_items_for_year(
                    year, hidden_fields
                )
                logger.info(f"Year {year}: {len(items)} gazette issues")
                for item in items:
                    yield item
                time.sleep(DELAY)
            except Exception as e:
                logger.warning(f"Failed to fetch year {year}: {e}")
                continue

    def _download_and_extract(self, pdf_url: str) -> str:
        """Download PDF and extract text."""
        session = self._get_session()
        try:
            resp = session.get(pdf_url, timeout=120)
            resp.raise_for_status()
            return _extract_pdf_text(resp.content)
        except Exception as e:
            logger.warning(f"Failed to download {pdf_url}: {e}")
            return ""

    def normalize(self, item: Dict, text: str) -> Dict:
        """Normalize a gazette item into a standard record."""
        iso_date = _parse_date(item["date"])
        issue_num = item["issue"]

        return {
            "_id": f"AE-DubaiGazette-{issue_num}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": f"Dubai Official Gazette - Issue No. {issue_num}",
            "text": text,
            "date": iso_date,
            "url": item["pdf_url"],
            "issue_number": issue_num,
            "year": int(item["pdf_url"].split("/")[-2])
            if "/" in item["pdf_url"]
            else None,
            "language": "ar",
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict, None, None]:
        """Fetch all gazette issues."""
        if sample:
            # For sample, just get recent issues from 2026
            years = [2026]
        else:
            years = None  # All years

        count = 0
        for item in self._get_all_gazette_items(years=years):
            logger.info(
                f"Downloading gazette issue #{item['issue']} ({item['date']})"
            )
            text = self._download_and_extract(item["pdf_url"])
            if not text:
                logger.warning(
                    f"No text extracted from issue #{item['issue']}, skipping"
                )
                continue

            record = self.normalize(item, text)
            yield record
            count += 1

            if sample and count >= 15:
                break

            time.sleep(DELAY)

        logger.info(f"Total records fetched: {count}")

    def fetch_updates(self, since: str) -> Generator[Dict, None, None]:
        """Fetch gazette issues published since a date."""
        since_dt = datetime.fromisoformat(since)
        current_year = datetime.now().year

        # Check current year and previous year
        years = [current_year, current_year - 1]

        for item in self._get_all_gazette_items(years=years):
            iso_date = _parse_date(item["date"])
            if iso_date and iso_date >= since:
                text = self._download_and_extract(item["pdf_url"])
                if text:
                    yield self.normalize(item, text)
                time.sleep(DELAY)

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            session = self._get_session()
            resp = session.get(GAZETTE_PAGE, timeout=15)
            resp.raise_for_status()
            items = _parse_gazette_items(resp.text)
            logger.info(f"Test OK: found {len(items)} gazette issues on default page")
            return len(items) > 0
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AE/DubaiLegalAffairs scraper")
    parser.add_argument("command", choices=["bootstrap", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Full fetch")
    args = parser.parse_args()

    scraper = DubaiLegalAffairsScraper()

    if args.command == "test":
        ok = scraper.test()
        sys.exit(0 if ok else 1)

    elif args.command == "bootstrap":
        sample = args.sample and not args.full
        out_dir = SAMPLE_DIR if sample else DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        records_file = out_dir / "records.jsonl"
        count = 0

        with open(records_file, "w", encoding="utf-8") as f:
            for record in scraper.fetch_all(sample=sample):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                logger.info(
                    f"[{count}] Issue #{record.get('issue_number')} "
                    f"({len(record.get('text', ''))} chars)"
                )

                # Also write individual sample files
                if sample:
                    sample_file = out_dir / f"{record['_id']}.json"
                    with open(sample_file, "w", encoding="utf-8") as sf:
                        json.dump(record, sf, indent=2, ensure_ascii=False)

        logger.info(f"Done. {count} records written to {records_file}")


if __name__ == "__main__":
    main()
