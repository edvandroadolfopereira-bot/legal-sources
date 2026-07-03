#!/usr/bin/env python3
"""
INTL/AJUDATA -- African Jurisprudence Database
(African Court on Human and Peoples' Rights)

Fetches decisions from the AJUDATA paginated JSON API, downloads
linked PDFs, and extracts full text via pdfplumber.

~470 decisions: judgments, orders, rulings, advisory opinions, provisional measures.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import io
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.AJUDATA")

API_URL = "https://www.african-court.org/ajudata/apidata/decisions"
SOURCE_ID = "INTL/AJUDATA"


class AJUDATAScraper(BaseScraper):
    """
    Scraper for INTL/AJUDATA -- African Court on Human and Peoples' Rights.
    Country: INTL
    URL: https://www.african-court.org/ajudata/

    Data types: case_law
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
        })

    def _fetch_decisions_page(self, page: int = 1) -> dict:
        """Fetch a single page from the decisions API."""
        resp = self.session.get(f"{API_URL}?page={page}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_best_pdf_url(self, decision: dict) -> Optional[str]:
        """
        Extract the best available PDF URL from a decision record.
        Prefers top-level full judgment over nested summaries.
        Tries EN > FR > PT > AR.
        """
        lang_keys = ["en_decision_file", "fr_decision_file", "pt_decision_file", "ar_decision_file"]

        # Top-level files are usually full judgments/orders
        for lang in lang_keys:
            f = decision.get(lang)
            if f and f.get("path"):
                return f["path"]

        # Nested files under legals[].decisions[] (often summaries, but better than nothing)
        for legal in decision.get("legals", []):
            for nested_dec in legal.get("decisions", []):
                for lang in lang_keys:
                    f = nested_dec.get(lang)
                    if f and f.get("path"):
                        return f["path"]

        return None

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                return "\n\n".join(pages_text) if pages_text else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return None

    def _build_title(self, decision: dict) -> str:
        """Build a human-readable title from the decision data."""
        # Try en_title first
        if decision.get("en_title"):
            return decision["en_title"].strip()

        # Build from legals data
        for legal in decision.get("legals", []):
            applicant = legal.get("applicant", {}).get("en_designation", "")
            defendants = [d.get("en_title", "") for d in legal.get("defendants", [])]
            case_num = legal.get("case_number", "")
            if applicant and defendants:
                resp_str = " & ".join(d for d in defendants if d)
                return f"Application {case_num} - {applicant} v. {resp_str}"
            elif applicant:
                return f"Application {case_num} - {applicant}"

        # Fallback
        dec_type = decision.get("decision_type", {}).get("en_designation", "Decision")
        return f"{dec_type} (ID {decision.get('id', 'unknown')})"

    def _extract_case_number(self, decision: dict) -> str:
        """Extract the primary case number."""
        for legal in decision.get("legals", []):
            cn = legal.get("case_number")
            if cn:
                return cn
        return f"DEC-{decision.get('id', 'unknown')}"

    def _extract_date(self, decision: dict) -> Optional[str]:
        """Extract decision date in ISO 8601 format."""
        raw = decision.get("decision_date")
        if raw:
            try:
                dt = datetime.strptime(raw.split(" ")[0], "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                pass
        return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions from the paginated API."""
        page = 1
        while True:
            logger.info(f"Fetching decisions page {page}...")
            try:
                data = self._fetch_decisions_page(page)
            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break

            records = data.get("data", [])
            if not records:
                break

            for decision in records:
                yield decision

            last_page = data.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(1)

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield decisions updated since the given date."""
        for decision in self.fetch_all():
            updated = decision.get("updated_at") or decision.get("created_at")
            if updated:
                try:
                    dt = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
                    if dt >= since:
                        yield decision
                except ValueError:
                    yield decision
            else:
                yield decision

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform a raw API decision into standardized schema."""
        decision_id = raw.get("id")
        if not decision_id:
            return None

        pdf_url = self._get_best_pdf_url(raw)
        text = None
        if pdf_url:
            self.rate_limiter.wait()
            text = self._extract_pdf_text(pdf_url)

        if not text or len(text) < 100:
            logger.debug(f"Skipping decision {decision_id}: no usable text from PDF")
            return None

        title = self._build_title(raw)
        case_number = self._extract_case_number(raw)
        date = self._extract_date(raw)
        decision_type = raw.get("decision_type", {}).get("en_designation", "")
        session_info = raw.get("session", {}).get("en_desc", "")

        # Extract applicant and respondent
        applicant = ""
        respondent_country = ""
        for legal in raw.get("legals", []):
            applicant = legal.get("applicant", {}).get("en_designation", "")
            defendants = [d.get("en_title", "") for d in legal.get("defendants", [])]
            respondent_country = "; ".join(d for d in defendants if d)
            break

        return {
            "_id": f"AJUDATA-{decision_id}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": f"https://www.african-court.org/ajudata/",
            "case_number": case_number,
            "decision_type": decision_type,
            "session": session_info,
            "applicant": applicant,
            "respondent_country": respondent_country,
            "pdf_url": pdf_url,
            "decision_year": raw.get("decision_year", ""),
        }


def main():
    parser = argparse.ArgumentParser(description="INTL/AJUDATA bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Full bootstrap (default)")
    args = parser.parse_args()

    scraper = AJUDATAScraper()

    if args.command == "test":
        logger.info("Testing AJUDATA API connectivity...")
        try:
            data = scraper._fetch_decisions_page(1)
            total = data.get("total", 0)
            logger.info(f"API OK: {total} total decisions, {data.get('last_page', 0)} pages")
        except Exception as e:
            logger.error(f"API test failed: {e}")
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = args.sample
        stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=15)
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")
    elif args.command == "update":
        since = datetime.now(timezone.utc).replace(day=1)
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
