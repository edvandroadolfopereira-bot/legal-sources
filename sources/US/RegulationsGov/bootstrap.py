#!/usr/bin/env python3
"""
US/RegulationsGov -- Federal Rulemaking Documents from Regulations.gov

Fetches federal rules, proposed rules, and notices via the Regulations.gov API v4,
then retrieves full text from the Federal Register API (free, no key needed).

Document counts: ~98K rules, ~49K proposed rules, ~383K notices.

Data access:
  - Regulations.gov API v4: /v4/documents (listing, metadata, docket info)
    Uses DEMO_KEY by default; set REGULATIONS_GOV_API_KEY env var for higher limits.
  - Federal Register API: /api/v1/documents/{fr_doc_num}.json (full text URLs)
  - Federal Register full text: HTML body at body_html_url

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from urllib.parse import quote

import requests

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.RegulationsGov")

SOURCE_ID = "US/RegulationsGov"
REGULATIONS_API = "https://api.regulations.gov/v4"
FR_API = "https://www.federalregister.gov/api/v1"
DELAY = 1.0
PAGE_SIZE = 25
MAX_PAGES_SAMPLE = 3
# Document types that appear in the Federal Register with full text
DOC_TYPES = ["Rule", "Proposed Rule", "Notice"]


def get_api_key() -> str:
    return os.environ.get("REGULATIONS_GOV_API_KEY", "DEMO_KEY")


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal-data-research)",
        "Accept": "application/json",
    })
    return session


def clean_html(html: str) -> str:
    """Strip HTML tags and clean up whitespace."""
    if not html:
        return ""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class RegulationsGovScraper:
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self.session = get_session()
        self.api_key = get_api_key()

    def _get(self, url: str, params: Optional[Dict] = None, timeout: int = 30) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    wait = 30 * (attempt + 1)
                    logger.warning("Rate limited, waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code == 403:
                    logger.warning("403 Forbidden for %s", url)
                    return None
                logger.warning("HTTP %d for %s", resp.status_code, url)
                return None
            except requests.RequestException as e:
                logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                time.sleep(5)
        return None

    def list_documents(self, doc_type: str, page_number: int = 1,
                       page_size: int = PAGE_SIZE, sort: str = "-postedDate") -> Dict[str, Any]:
        """List documents from Regulations.gov API."""
        params = {
            "filter[documentType]": doc_type,
            "api_key": self.api_key,
            "page[size]": page_size,
            "page[number]": page_number,
            "sort": sort,
        }
        resp = self._get(f"{REGULATIONS_API}/documents", params=params)
        if not resp:
            return {"data": [], "meta": {}}
        return resp.json()

    def get_document_detail(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document detail from Regulations.gov API."""
        params = {"api_key": self.api_key}
        resp = self._get(f"{REGULATIONS_API}/documents/{doc_id}", params=params)
        if not resp:
            return None
        return resp.json().get("data", {}).get("attributes", {})

    def get_fr_full_text(self, fr_doc_num: str) -> Optional[str]:
        """Fetch full text from Federal Register API using FR document number."""
        if not fr_doc_num:
            return None

        # Get the document metadata from FR API to find full text URLs
        fields = "body_html_url,raw_text_url,full_text_xml_url,title,abstract"
        resp = self._get(
            f"{FR_API}/documents/{fr_doc_num}.json",
            params={"fields[]": fields.split(",")},
        )
        if not resp:
            return None

        data = resp.json()
        body_html_url = data.get("body_html_url")
        raw_text_url = data.get("raw_text_url")

        # Prefer HTML body (structured), fall back to raw text
        if body_html_url:
            time.sleep(0.5)
            html_resp = self._get(body_html_url, timeout=60)
            if html_resp:
                text = clean_html(html_resp.text)
                if len(text) > 100:
                    return text

        if raw_text_url:
            time.sleep(0.5)
            txt_resp = self._get(raw_text_url, timeout=60)
            if txt_resp:
                text = txt_resp.text.strip()
                if len(text) > 100:
                    return text

        return None

    def normalize(self, listing: Dict[str, Any], detail: Optional[Dict[str, Any]],
                  full_text: str) -> Dict[str, Any]:
        """Normalize a Regulations.gov document into standard schema."""
        attrs = listing.get("attributes", {})
        doc_id = listing.get("id", "")

        posted_date = attrs.get("postedDate", "")
        if posted_date:
            try:
                posted_date = posted_date[:10]  # YYYY-MM-DD
            except (IndexError, TypeError):
                posted_date = None

        # Get additional metadata from detail if available
        fr_doc_num = attrs.get("frDocNum", "")
        agency_id = attrs.get("agencyId", "")
        docket_id = attrs.get("docketId", "")
        doc_type = attrs.get("documentType", "")
        subtype = attrs.get("subtype", "")

        # Build URL
        url = f"https://www.regulations.gov/document/{doc_id}"

        record = {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": attrs.get("title", ""),
            "text": full_text,
            "date": posted_date,
            "url": url,
            "agency_id": agency_id,
            "document_type": doc_type,
            "subtype": subtype or None,
            "docket_id": docket_id,
            "fr_doc_num": fr_doc_num or None,
            "comment_end_date": attrs.get("commentEndDate"),
            "open_for_comment": attrs.get("openForComment", False),
        }

        # Add detail fields if available
        if detail:
            record["abstract"] = detail.get("docAbstract") or None
            record["cfr_part"] = detail.get("cfrPart") or None
            record["effective_date"] = detail.get("effectiveDate") or None
            record["authors"] = detail.get("authors") or None

        return record

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Yield all documents with full text."""
        max_pages = MAX_PAGES_SAMPLE if sample else 10000
        records_yielded = 0
        target = 15 if sample else float("inf")

        for doc_type in DOC_TYPES:
            if records_yielded >= target:
                break

            logger.info("Fetching %s documents...", doc_type)
            page = 1

            while page <= max_pages and records_yielded < target:
                time.sleep(DELAY)
                result = self.list_documents(doc_type, page_number=page)
                docs = result.get("data", [])
                meta = result.get("meta", {})

                if not docs:
                    logger.info("No more %s documents at page %d", doc_type, page)
                    break

                for doc in docs:
                    if records_yielded >= target:
                        break

                    doc_id = doc.get("id", "")
                    fr_doc_num = doc.get("attributes", {}).get("frDocNum")

                    if not fr_doc_num:
                        logger.debug("Skipping %s (no FR doc number)", doc_id)
                        continue

                    # Fetch full text from Federal Register
                    time.sleep(DELAY)
                    full_text = self.get_fr_full_text(fr_doc_num)

                    if not full_text or len(full_text) < 100:
                        logger.warning("No full text for %s (FR: %s)", doc_id, fr_doc_num)
                        continue

                    # Get detail for extra metadata (skip in sample to save API calls)
                    detail = None
                    if not sample:
                        time.sleep(DELAY)
                        detail = self.get_document_detail(doc_id)

                    record = self.normalize(doc, detail, full_text)
                    records_yielded += 1
                    logger.info(
                        "[%d] %s: %s (%d chars)",
                        records_yielded, doc_id,
                        record["title"][:60], len(full_text),
                    )
                    yield record

                has_next = meta.get("hasNextPage", False)
                if not has_next:
                    break
                page += 1

        logger.info("Total records yielded: %d", records_yielded)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Yield documents modified since a date."""
        for doc_type in DOC_TYPES:
            logger.info("Fetching %s updates since %s...", doc_type, since)
            page = 1
            while True:
                time.sleep(DELAY)
                result = self.list_documents(doc_type, page_number=page)
                docs = result.get("data", [])
                meta = result.get("meta", {})

                if not docs:
                    break

                for doc in docs:
                    posted = doc.get("attributes", {}).get("postedDate", "")
                    if posted and posted[:10] < since:
                        return

                    fr_doc_num = doc.get("attributes", {}).get("frDocNum")
                    if not fr_doc_num:
                        continue

                    time.sleep(DELAY)
                    full_text = self.get_fr_full_text(fr_doc_num)
                    if not full_text or len(full_text) < 100:
                        continue

                    time.sleep(DELAY)
                    detail = self.get_document_detail(doc.get("id", ""))
                    yield self.normalize(doc, detail, full_text)

                if not meta.get("hasNextPage", False):
                    break
                page += 1

    def test(self) -> bool:
        """Quick connectivity test."""
        logger.info("Testing Regulations.gov API...")
        result = self.list_documents("Rule", page_size=5)
        docs = result.get("data", [])
        if not docs:
            logger.error("No documents returned from API")
            return False

        logger.info("API OK: %d rules returned", len(docs))

        # Test FR API cross-reference
        fr_num = docs[0].get("attributes", {}).get("frDocNum")
        if fr_num:
            logger.info("Testing Federal Register API with FR# %s...", fr_num)
            text = self.get_fr_full_text(fr_num)
            if text and len(text) > 100:
                logger.info("FR API OK: %d chars of full text", len(text))
                return True
            else:
                logger.error("Failed to get full text from Federal Register")
                return False
        else:
            logger.warning("First document has no FR doc number")
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="US/RegulationsGov data fetcher")
    parser.add_argument("command", choices=["bootstrap", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch only 10-15 sample records")
    parser.add_argument("--since", type=str, default=None,
                        help="ISO date for incremental updates (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSONL file path")
    args = parser.parse_args()

    scraper = RegulationsGovScraper()

    if args.command == "test":
        ok = scraper.test()
        sys.exit(0 if ok else 1)

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command == "bootstrap":
        records = scraper.fetch_all(sample=args.sample)
    elif args.command == "update":
        since = args.since or "2024-01-01"
        records = scraper.fetch_updates(since)
    else:
        parser.print_help()
        sys.exit(1)

    output_path = args.output
    if output_path:
        outfile = open(output_path, "w")
    else:
        outfile = None

    count = 0
    for record in records:
        count += 1

        # Save to sample directory
        if args.sample or count <= 15:
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", record["_id"])
            sample_path = sample_dir / f"{safe_id}.json"
            with open(sample_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

        # Write to JSONL if output specified
        if outfile:
            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")

    if outfile:
        outfile.close()

    logger.info("Done. %d records processed.", count)
    if count == 0:
        logger.error("No records fetched — check API connectivity and rate limits")
        sys.exit(1)


if __name__ == "__main__":
    main()
