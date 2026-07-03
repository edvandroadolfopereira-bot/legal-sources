#!/usr/bin/env python3
"""
US/PCAOB-Enforcement -- PCAOB Enforcement Actions

Fetches enforcement orders from the PCAOB via HawkSearch API + PDF extraction.
~555 enforcement documents: settled disciplinary orders, adjudicated orders,
and termination of bars. Full text extracted from official PDF orders.

Data access:
  - HawkSearch API: POST https://essearchapi-na.hawksearch.com/api/v2/search/
  - PDF orders: https://assets.pcaobus.org/pcaob-dev/docs/default-source/enforcement/...
  - Client GUID: e962e95324cb46ef8955c0b09a3904b9

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import time
import re
import io
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests
import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.PCAOB-Enforcement")

SEARCH_API = "https://essearchapi-na.hawksearch.com/api/v2/search/"
CLIENT_GUID = "e962e95324cb46ef8955c0b09a3904b9"
INDEX_NAME = "pcaob.20260515.140735.all-data-types"
PER_PAGE = 24  # HawkSearch default page size
DELAY = 1.5

SOURCE_ID = "US/PCAOB-Enforcement"
SAMPLE_DIR = Path(__file__).parent / "sample"

ENFORCEMENT_TYPES = [
    "Settled Disciplinary Order",
    "Adjudicated Disciplinary Order",
    "Termination of Bars",
]


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    return session


def extract_pdf_text(session: requests.Session, url: str) -> Optional[str]:
    """Download PDF and extract full text using pdfplumber."""
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60)
            if resp.status_code != 200:
                logger.warning("PDF HTTP %d: %s", resp.status_code, url)
                return None
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                full_text = "\n\n".join(pages)
                if len(full_text.strip()) < 50:
                    logger.warning("PDF text too short (%d chars): %s", len(full_text), url)
                    return None
                return full_text.strip()
        except Exception as e:
            logger.warning("PDF extraction error (attempt %d): %s", attempt + 1, e)
            time.sleep(3)
    return None


class PCAOBEnforcementScraper:
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self.session = get_session()

    def search_enforcement(self, page: int = 1, max_per_page: int = PER_PAGE,
                           order_type: Optional[str] = None) -> Dict[str, Any]:
        """Query the HawkSearch API for enforcement documents."""
        facets = {"contenttypelabel": ["Enforcement Document"]}
        if order_type:
            facets["enforcementordertypes"] = [order_type]

        payload = {
            "ClientGuid": CLIENT_GUID,
            "Keyword": "",
            "MaxPerPage": max_per_page,
            "PageNo": page,
            "FacetSelections": facets,
            "IndexName": INDEX_NAME,
        }

        for attempt in range(3):
            try:
                resp = self.session.post(SEARCH_API, json=payload, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning("Search API HTTP %d (attempt %d)", resp.status_code, attempt + 1)
            except requests.RequestException as e:
                logger.warning("Search API error (attempt %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
        return {}

    def parse_document(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a HawkSearch result document into our record format."""
        def first(val):
            if isinstance(val, list):
                return val[0] if val else ""
            return val or ""

        title = first(doc.get("title"))
        unique_id = first(doc.get("unique_id"))
        effective_date = first(doc.get("effectivedate"))
        order_type = first(doc.get("enforcementordertypes"))
        doc_json_str = first(doc.get("enforcementorderdocument"))

        if not title or not unique_id:
            return None

        # Parse the embedded JSON for the PDF document
        pdf_url = None
        doc_title = None
        if doc_json_str:
            try:
                doc_info = json.loads(doc_json_str)
                pdf_url = doc_info.get("mediaUrl", "")
                doc_title = doc_info.get("title", "")
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse date
        date_str = None
        if effective_date:
            try:
                dt = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_str = effective_date[:10] if len(effective_date) >= 10 else None

        return {
            "unique_id": unique_id,
            "title": title,
            "date": date_str,
            "enforcement_type": order_type,
            "pdf_url": pdf_url,
            "doc_title": doc_title,
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Fetch all enforcement documents with full text from PDFs."""
        sample_limit = 15 if sample else None
        count = 0

        # Get total count first
        initial = self.search_enforcement(page=1, max_per_page=1)
        total = initial.get("Pagination", {}).get("NofResults", 0)
        logger.info("Total enforcement documents: %d", total)

        page = 1
        while True:
            if sample_limit and count >= sample_limit:
                break

            data = self.search_enforcement(page=page, max_per_page=PER_PAGE)
            results = data.get("Results", [])
            if not results:
                break

            pagination = data.get("Pagination", {})
            total_pages = pagination.get("NofPages", 1)
            logger.info("Page %d/%d — %d results", page, total_pages, len(results))

            for result in results:
                if sample_limit and count >= sample_limit:
                    break

                doc = result.get("Document", {})
                parsed = self.parse_document(doc)
                if not parsed:
                    continue

                # Download and extract PDF text
                text = None
                if parsed["pdf_url"]:
                    text = extract_pdf_text(self.session, parsed["pdf_url"])
                    time.sleep(DELAY)

                if not text:
                    logger.warning("No text extracted for: %s", parsed["title"])
                    continue

                record = self.normalize(parsed, text)
                count += 1
                logger.info("[%d] %s — %d chars", count, parsed["title"], len(text))
                yield record

            if page >= total_pages:
                break
            page += 1
            time.sleep(DELAY)

        logger.info("Fetched %d enforcement documents with full text", count)

    def normalize(self, parsed: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Normalize a parsed enforcement document into standard schema."""
        # Clean order number from doc_title for a stable ID
        doc_title = parsed.get("doc_title", "") or ""
        # Extract order number like "105-2026-001"
        order_match = re.search(r"(105-\d{4}-\d{3})", doc_title)
        order_number = order_match.group(1) if order_match else parsed["unique_id"]

        url = parsed.get("pdf_url", "")
        # Strip query string for cleaner URL
        if "?" in url:
            url = url.split("?")[0]

        return {
            "_id": f"pcaob-{order_number}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": parsed["title"],
            "date": parsed["date"],
            "text": text,
            "url": url,
            "enforcement_type": parsed["enforcement_type"],
            "order_number": order_number,
        }


def cmd_test():
    """Quick connectivity test."""
    scraper = PCAOBEnforcementScraper()
    data = scraper.search_enforcement(page=1, max_per_page=1)
    total = data.get("Pagination", {}).get("NofResults", 0)
    results = data.get("Results", [])
    if total > 0 and results:
        doc = results[0].get("Document", {})
        title = doc.get("title", [""])[0] if isinstance(doc.get("title"), list) else doc.get("title", "")
        print(f"OK: {total} enforcement documents available. First: {title}")
    else:
        print("FAIL: Could not reach HawkSearch API")
        sys.exit(1)


def cmd_bootstrap(sample: bool = False):
    """Full bootstrap: fetch all enforcement documents."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    scraper = PCAOBEnforcementScraper()
    count = 0
    for record in scraper.fetch_all(sample=sample):
        out_path = SAMPLE_DIR / f"{record['_id']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        count += 1
    print(f"Done: {count} records saved to {SAMPLE_DIR}")


def main():
    if len(sys.argv) < 2:
        print("Usage: bootstrap.py {test|bootstrap|bootstrap-fast|update} [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        cmd_test()
    elif command in ("bootstrap", "bootstrap-fast"):
        cmd_bootstrap(sample=sample)
    elif command == "update":
        cmd_bootstrap(sample=sample)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
