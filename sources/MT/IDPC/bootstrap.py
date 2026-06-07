#!/usr/bin/env python3
"""
MT/IDPC -- Malta Information & Data Protection Commissioner — GDPR Decisions

Fetches GDPR enforcement decisions from https://idpc.org.mt/decisions/.

Strategy:
  - Parse the decisions table from the /decisions/ page HTML
  - Table columns: Year, Type, Description, Outcome, Corrective Action, Decision (PDF link)
  - For entries with PDFs, download and extract full text
  - For entries without PDFs, use table text (Description + Outcome + Corrective Action)
  - ~254 decisions total

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, List

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.MT.IDPC")

DECISIONS_URL = "https://idpc.org.mt/decisions/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}


class IDPCScraper(BaseScraper):
    SOURCE_ID = "MT/IDPC"

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch_page(self, url: str) -> Optional[str]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if attempt == 2:
                    logger.warning("Failed to fetch %s: %s", url, e)
                    return None
                time.sleep(2 * (attempt + 1))

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Extract text from a PDF decision document."""
        text = extract_pdf_markdown(
            source="MT/IDPC",
            source_id="",
            pdf_url=pdf_url,
            table="doctrine",
        )
        return text or ""

    def _parse_decisions_table(self) -> List[Dict]:
        """Parse all decisions from the /decisions/ page table."""
        logger.info("Fetching decisions page: %s", DECISIONS_URL)
        html = self._fetch_page(DECISIONS_URL)
        if not html:
            logger.error("Could not fetch decisions page")
            return []

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr", class_=re.compile(r"^row-"))

        decisions = []
        row_num = 0

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            row_num += 1
            year = cells[0].get_text(strip=True)
            decision_type = cells[1].get_text(strip=True)
            description = cells[2].get_text(strip=True)
            outcome = cells[3].get_text(strip=True)
            corrective_action = cells[4].get_text(strip=True)

            # Get PDF link if present
            pdf_url = None
            if len(cells) > 5:
                pdf_link = cells[5].find("a", href=re.compile(r"\.pdf$"))
                if pdf_link:
                    pdf_url = pdf_link["href"]

            # Extract case reference from PDF filename if available
            case_ref = ""
            if pdf_url:
                fname = pdf_url.split("/")[-1].replace(".pdf", "")
                # Clean up filename to get case ref
                case_ref = re.sub(r"[-_]?[Rr]edacted[-_]?", "", fname)
                case_ref = re.sub(r"^\d{4}_\d{3}$", fname, case_ref)

            decisions.append({
                "row_num": row_num,
                "year": year,
                "decision_type": decision_type,
                "description": description,
                "outcome": outcome,
                "corrective_action": corrective_action,
                "pdf_url": pdf_url,
                "case_ref": case_ref,
            })

        logger.info("Parsed %d decisions from table", len(decisions))
        return decisions

    def test_connection(self) -> bool:
        try:
            html = self._fetch_page(DECISIONS_URL)
            if html and "IDPC" in html:
                logger.info("Connection OK: IDPC decisions page accessible")
                return True
            return False
        except Exception as e:
            logger.error("Connection failed: %s", e)
            return False

    def fetch_all(self) -> Generator[Dict, None, None]:
        decisions = self._parse_decisions_table()
        if not decisions:
            return

        logger.info("Processing %d decisions...", len(decisions))
        for i, dec in enumerate(decisions):
            logger.info("[%d/%d] Row %d: %s (%s)",
                        i + 1, len(decisions), dec["row_num"],
                        dec["decision_type"][:30], dec["year"])

            # Build text from table metadata
            table_text = (
                f"Type: {dec['decision_type']}\n\n"
                f"Description: {dec['description']}\n\n"
                f"Outcome: {dec['outcome']}\n\n"
                f"Corrective Action: {dec['corrective_action']}"
            )

            # Try to get full text from PDF if available
            full_text = ""
            if dec["pdf_url"]:
                self.rate_limiter.wait()
                logger.info("  Downloading PDF: %s", dec["pdf_url"].split("/")[-1])
                full_text = self._extract_pdf_text(dec["pdf_url"])

            # Use table text if no PDF or PDF extraction failed
            if not full_text or len(full_text) < 100:
                full_text = table_text

            dec["text"] = full_text
            dec["table_text"] = table_text
            yield dec

    def fetch_updates(self, since: datetime) -> Generator[Dict, None, None]:
        return
        yield

    def normalize(self, raw: dict) -> dict:
        row_num = raw["row_num"]
        case_ref = raw.get("case_ref", "")
        doc_id = case_ref if case_ref else f"row-{row_num}"

        # Build a descriptive title
        desc_short = raw["description"][:80].rstrip()
        title = f"IDPC Decision {raw['year']}: {desc_short}"

        date_str = f"{raw['year']}-01-01" if raw["year"].isdigit() else None

        return {
            "_id": f"MT-IDPC-{doc_id}",
            "_source": "MT/IDPC",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw["text"],
            "date": date_str,
            "url": raw.get("pdf_url") or DECISIONS_URL,
            "decision_type": raw.get("decision_type", ""),
            "outcome": raw.get("outcome", ""),
            "corrective_action": raw.get("corrective_action", ""),
            "case_ref": raw.get("case_ref", ""),
        }

    def run_bootstrap(self, sample: bool = False):
        sample_dir = self.source_dir / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for raw in self.fetch_all():
            normalized = self.normalize(raw)
            fname = re.sub(r"[^\w\-.]", "_", f"{normalized['_id'][:80]}.json")
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            count += 1
            logger.info("  -> %d chars of text", len(normalized["text"]))

            if sample and count >= 15:
                break

        logger.info("Bootstrap complete: %d records saved", count)
        return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MT/IDPC Bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = IDPCScraper()

    if args.command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.run_bootstrap(sample=args.sample)
    elif args.command == "update":
        scraper.run_bootstrap(sample=False)


if __name__ == "__main__":
    main()
