#!/usr/bin/env python3
"""
INTL/UNCC -- UN Compensation Commission Governing Council Decisions

Fetches decision PDFs from the UNCC website (uncc.un.org).

Strategy:
  1. Scrape the decisions listing page for all PDF links
  2. Download each PDF and extract full text using PyMuPDF
  ~279 decisions (1991–2022). Static archive (mandate concluded 2022).

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample  # Fetch 15 sample records
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.UNCC")

BASE_URL = "https://uncc.un.org"
DECISIONS_URL = f"{BASE_URL}/en/documents/decisions-governing-council"
DELAY = 2.0


class UNCCScraper(BaseScraper):
    SOURCE_ID = "INTL/UNCC"

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _discover_decisions(self) -> List[dict]:
        """Scrape the decisions listing page for all decision PDF links."""
        r = self.session.get(DECISIONS_URL, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        main = soup.find("main") or soup

        decisions = []
        seen_urls = set()

        for a in main.find_all("a", href=True):
            href = a["href"]
            if ".pdf" not in href.lower():
                continue
            text = a.get_text(strip=True)
            # Only decision PDFs (not panel reports, statements, etc.)
            if not (re.search(r"dec", href.lower()) or "decision" in text.lower()):
                continue

            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract decision number and year from link text
            # Format: "Decision 277 (2022)" or "Decision 5 (1991)"
            m = re.search(r"Decision\s+(\d+)\s*\((\d{4})\)", text)
            dec_num = int(m.group(1)) if m else None
            year = m.group(2) if m else None

            decisions.append({
                "title": text,
                "pdf_url": full_url,
                "dec_num": dec_num,
                "year": year,
            })

        # Sort by decision number (ascending)
        decisions.sort(key=lambda d: d.get("dec_num") or 0)
        logger.info("Discovered %d decisions", len(decisions))
        return decisions

    # ------------------------------------------------------------------ #
    # PDF text extraction
    # ------------------------------------------------------------------ #

    def _extract_pdf_text(self, url: str) -> Optional[str]:
        """Download a PDF and extract full text using PyMuPDF."""
        try:
            r = self.session.get(url, timeout=120)
            r.raise_for_status()

            if len(r.content) < 100:
                logger.warning("PDF too small (%d bytes): %s", len(r.content), url)
                return None

            doc = fitz.open(stream=r.content, filetype="pdf")
            text_parts = []
            for page in doc:
                t = page.get_text()
                if t:
                    text_parts.append(t)
            doc.close()

            text = "\n".join(text_parts).strip()
            if len(text) < 50:
                logger.warning("PDF extraction yielded only %d chars: %s", len(text), url)
                return None

            return text

        except Exception as e:
            logger.warning("PDF extraction failed for %s: %s", url, e)
            return None

    # ------------------------------------------------------------------ #
    # Normalization
    # ------------------------------------------------------------------ #

    def normalize(self, raw: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        dec_num = raw.get("dec_num")
        doc_id = f"UNCC-DEC-{dec_num}" if dec_num else f"UNCC-{raw['title'][:30]}"

        date = None
        if raw.get("year"):
            date = f"{raw['year']}-01-01"

        return {
            "_id": doc_id,
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": now,
            "title": raw["title"],
            "text": raw.get("text", ""),
            "date": date,
            "url": raw["pdf_url"],
            "decision_number": dec_num,
            "year": raw.get("year"),
        }

    # ------------------------------------------------------------------ #
    # Main fetch logic
    # ------------------------------------------------------------------ #

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all UNCC decisions with full text."""
        decisions = self._discover_decisions()
        if not decisions:
            logger.error("No decisions found")
            return

        if sample:
            # Take 15 spread across the collection
            step = max(1, len(decisions) // 15)
            decisions = decisions[::step][:15]
            logger.info("Sample mode: %d decisions selected", len(decisions))

        count = 0
        skipped = 0

        for d in decisions:
            time.sleep(DELAY)
            text = self._extract_pdf_text(d["pdf_url"])
            if not text:
                skipped += 1
                continue

            d["text"] = text
            record = self.normalize(d)
            count += 1
            yield record

        logger.info("Done: %d records yielded, %d skipped, %d total", count, skipped, len(decisions))

    def fetch_updates(self, since) -> Generator[dict, None, None]:
        """Mandate concluded in 2022 — re-fetch all."""
        yield from self.fetch_all(sample=False)

    def test_connection(self) -> bool:
        try:
            r = self.session.get(DECISIONS_URL, timeout=15)
            return r.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------- #
# CLI entry point
# ---------------------------------------------------------------------- #

def main():
    scraper = UNCCScraper()
    args = sys.argv[1:]

    if not args or args[0] == "test":
        ok = scraper.test_connection()
        print(f"Connection test: {'OK' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)

    sample = "--sample" in args
    command = args[0]

    if command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            out_path = sample_dir / f"{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            text_len = len(record.get("text", ""))
            logger.info("[%d] %s — %d chars", count, record["title"], text_len)
        print(f"\nBootstrap complete: {count} records saved to sample/")

    elif command in ("update", "bootstrap-fast"):
        count = 0
        for record in scraper.fetch_updates(None):
            count += 1
            print(json.dumps(record, ensure_ascii=False))
        logger.info("Update complete: %d records", count)

    else:
        print(f"Unknown command: {command}")
        print("Usage: bootstrap.py [bootstrap|update|test] [--sample]")
        sys.exit(1)


if __name__ == "__main__":
    main()
