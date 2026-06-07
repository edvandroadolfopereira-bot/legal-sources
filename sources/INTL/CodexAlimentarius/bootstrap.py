#!/usr/bin/env python3
"""
INTL/CodexAlimentarius -- FAO/WHO Codex Alimentarius Commission
                          International Food Standards

Fetches all Codex Alimentarius standards (CXS), guidelines (CXG), and
codes of practice (CXC) from the FAO website.  Full text is extracted
from official PDFs served via the FAO proxy.

Strategy:
  - Parse the HTML table on each of three listing pages:
        /codex-texts/list-standards/en/
        /codex-texts/guidelines/en/
        /codex-texts/codes-of-practice/en/
  - For each row, extract reference, title, committee, last-modified year,
    and the English PDF download link (via the FAO sh-proxy).
  - Download the PDF and extract text using pdfminer.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records
  python bootstrap.py update             # Re-scan listings
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.CodexAlimentarius")

BASE_URL = "https://www.fao.org"

# Three listing pages with their document type labels
LISTING_PAGES = [
    (
        "/fao-who-codexalimentarius/codex-texts/list-standards/en/",
        "standard",
    ),
    (
        "/fao-who-codexalimentarius/codex-texts/guidelines/en/",
        "guideline",
    ),
    (
        "/fao-who-codexalimentarius/codex-texts/codes-of-practice/en/",
        "code_of_practice",
    ),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}

MIN_TEXT_CHARS = 200


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer."""
    import io
    from pdfminer.high_level import extract_text

    with io.BytesIO(pdf_bytes) as f:
        text = extract_text(f)
    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _parse_listing_page(html: str, doc_type: str) -> list[dict]:
    """
    Parse a Codex listing page HTML and extract document metadata.

    Returns a list of dicts with keys:
      reference, title, committee, last_modified, pdf_url, doc_type
    """
    soup = BeautifulSoup(html, "html.parser")

    # The standards data is in an HTML table — find all <tr> rows
    rows = soup.find_all("tr")
    documents = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        reference = cells[0].get_text(strip=True)
        # Must match Codex reference pattern (CXS/CXG/CXC/CXA + number)
        if not re.match(r"CX[SGCA]\s+\d+", reference):
            continue

        title = cells[1].get_text(strip=True)
        committee = cells[2].get_text(strip=True)
        last_modified = cells[3].get_text(strip=True)

        # Find the English PDF link (first <a> with an href containing .pdf)
        # Language order in the table: EN, FR, ES, AR, ZH, RU
        pdf_url = None
        link_cell = cells[4] if len(cells) > 4 else None
        if link_cell:
            links = link_cell.find_all("a", href=True)
            if links:
                # First link is English
                pdf_url = links[0]["href"]
                if not pdf_url.startswith("http"):
                    pdf_url = BASE_URL + pdf_url

        if not pdf_url:
            logger.warning(f"No PDF link for {reference}, skipping")
            continue

        documents.append({
            "reference": reference,
            "title": title,
            "committee": committee,
            "last_modified": last_modified,
            "pdf_url": pdf_url,
            "doc_type": doc_type,
        })

    return documents


class CodexAlimentariusScraper(BaseScraper):
    """
    Scraper for INTL/CodexAlimentarius.
    Country: INTL
    URL: https://www.fao.org/fao-who-codexalimentarius/codex-texts/en/
    Data types: legislation
    """

    SOURCE_ID = "INTL/CodexAlimentarius"

    def __init__(self, source_dir: Optional[str] = None):
        if source_dir is None:
            source_dir = str(Path(__file__).parent)
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_all_documents(self) -> list[dict]:
        """Fetch and parse all three listing pages, return combined document list."""
        all_docs = []

        for path, doc_type in LISTING_PAGES:
            url = BASE_URL + path
            logger.info(f"Fetching listing: {url}")
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            time.sleep(1)

            docs = _parse_listing_page(resp.text, doc_type)
            logger.info(f"  Found {len(docs)} {doc_type} documents")
            all_docs.extend(docs)

        logger.info(f"Total documents found: {len(all_docs)}")
        return all_docs

    def _download_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download PDF via the FAO proxy and extract text."""
        try:
            resp = self.session.get(pdf_url, timeout=120)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                logger.warning(f"Response is not a PDF: {content_type}")
                return None

            text = _extract_text_from_pdf(resp.content)
            return text if len(text) >= MIN_TEXT_CHARS else None
        except Exception as e:
            logger.error(f"PDF download/extract failed for {pdf_url}: {e}")
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all Codex Alimentarius documents with full text."""
        documents = self._get_all_documents()

        for i, doc in enumerate(documents):
            logger.info(
                f"[{i + 1}/{len(documents)}] Downloading {doc['reference']}: "
                f"{doc['title'][:60]}..."
            )
            self.rate_limiter.wait()

            text = self._download_pdf_text(doc["pdf_url"])
            if not text:
                logger.warning(f"  No text extracted for {doc['reference']}, skipping")
                continue

            doc["text"] = text
            logger.info(f"  Extracted {len(text):,} chars")
            yield doc

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield documents modified since the given date."""
        documents = self._get_all_documents()

        for doc in documents:
            # Filter by last_modified year
            try:
                mod_year = int(doc["last_modified"])
                if mod_year < since.year:
                    continue
            except (ValueError, TypeError):
                pass  # Can't parse year, include it

            self.rate_limiter.wait()
            text = self._download_pdf_text(doc["pdf_url"])
            if not text:
                continue

            doc["text"] = text
            yield doc

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        reference = raw["reference"]
        last_modified = raw.get("last_modified", "")

        # Build date from last_modified year
        date_str = None
        if last_modified and last_modified.isdigit():
            date_str = f"{last_modified}-01-01"

        # Build a stable ID from the reference
        doc_id = re.sub(r"[^A-Za-z0-9]+", "-", reference).strip("-")

        return {
            "_id": doc_id,
            "_source": self.SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "reference": reference,
            "date": date_str,
            "url": raw["pdf_url"],
            "committee": raw.get("committee", ""),
            "doc_type": raw.get("doc_type", "standard"),
            "last_modified_year": last_modified,
        }


# ── CLI entrypoint ──────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="INTL/CodexAlimentarius bootstrap"
    )
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "test"],
        help="Command to run",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Fetch only sample records",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=15,
        help="Number of sample records to fetch",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch all records (no limit)",
    )
    args = parser.parse_args()

    scraper = CodexAlimentariusScraper()

    if args.command == "test":
        logger.info("Testing connectivity...")
        resp = scraper.session.get(
            BASE_URL + LISTING_PAGES[0][0], timeout=30
        )
        logger.info(f"Standards page: HTTP {resp.status_code}")
        docs = _parse_listing_page(resp.text, "standard")
        logger.info(f"Parsed {len(docs)} standards from page")
        if docs:
            logger.info(f"First: {docs[0]['reference']} — {docs[0]['title']}")
        return

    if args.command == "bootstrap":
        stats = scraper.bootstrap(
            sample_mode=args.sample,
            sample_size=args.sample_size,
        )
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
