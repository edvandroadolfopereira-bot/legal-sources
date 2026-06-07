#!/usr/bin/env python3
"""
INTL/AU-Decisions -- African Union Assembly Decisions & Resolutions

Fetches AU Assembly decisions, declarations, and resolutions from the
AU Digital Archives (DSpace) via the DSpace REST API.

Strategy:
  - Paginate through the Assembly Collection using DSpace REST API
  - For each item, extract Dublin Core metadata
  - Fetch pre-extracted text from TEXT bundle bitstreams
  - Fall back to PDF download + pdfplumber extraction if no TEXT bitstream

Data:
  - ~1,689 items in Assembly Collection (1964-2026)
  - Multiple languages (EN, FR, AR, PT, ES, SW)
  - No authentication required

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch all (same as bootstrap)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.AU-Decisions")

BASE_URL = "https://archives.au.int"
REST_BASE = BASE_URL + "/rest"
ASSEMBLY_COLLECTION_UUID = "a627713a-11ad-4c62-87a2-7bfb16836ee4"
PAGE_SIZE = 50


class AUDecisionsScraper(BaseScraper):
    """Scraper for INTL/AU-Decisions -- African Union Assembly Decisions."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; contact@legaldatahunter.com)",
            "Accept": "application/json",
        })

    def _get_metadata_value(self, metadata: List[Dict], key: str) -> Optional[str]:
        """Extract first value for a Dublin Core key from DSpace metadata."""
        for entry in metadata:
            if entry.get("key") == key:
                return entry.get("value")
        return None

    def _get_metadata_values(self, metadata: List[Dict], key: str) -> List[str]:
        """Extract all values for a Dublin Core key from DSpace metadata."""
        return [e["value"] for e in metadata if e.get("key") == key]

    def _fetch_text_from_bitstreams(self, bitstreams: List[Dict]) -> Optional[str]:
        """Try to get pre-extracted text from TEXT bundle bitstreams."""
        for bs in bitstreams:
            if bs.get("bundleName") == "TEXT" and bs.get("mimeType", "").startswith("text/"):
                retrieve_link = bs.get("retrieveLink")
                if retrieve_link:
                    url = BASE_URL + retrieve_link
                    try:
                        self.rate_limiter.wait()
                        resp = self.session.get(url, timeout=30)
                        resp.raise_for_status()
                        text = resp.text.strip()
                        if len(text) > 50:
                            return text
                    except Exception as e:
                        logger.warning("Failed to fetch TEXT bitstream: %s", e)
        return None

    def _fetch_pdf_text(self, bitstreams: List[Dict]) -> Optional[str]:
        """Download original PDF and extract text via pdfplumber."""
        for bs in bitstreams:
            if bs.get("bundleName") == "ORIGINAL" and bs.get("mimeType") == "application/pdf":
                retrieve_link = bs.get("retrieveLink")
                if retrieve_link:
                    url = BASE_URL + retrieve_link
                    try:
                        self.rate_limiter.wait()
                        resp = self.session.get(url, timeout=60)
                        resp.raise_for_status()
                        try:
                            from common.pdf_extract import extract_pdf_markdown
                            text = extract_pdf_markdown(resp.content)
                            if text and len(text.strip()) > 50:
                                return text.strip()
                        except ImportError:
                            import io
                            try:
                                import pdfplumber
                                with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                                    pages = [p.extract_text() or "" for p in pdf.pages]
                                text = "\n\n".join(pages).strip()
                                if len(text) > 50:
                                    return text
                            except ImportError:
                                logger.warning("No PDF extraction library available")
                    except Exception as e:
                        logger.warning("Failed to fetch PDF: %s", e)
        return None

    def _fetch_items(self, limit: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
        """Paginate through the Assembly Collection items."""
        offset = 0
        fetched = 0
        url = f"{REST_BASE}/collections/{ASSEMBLY_COLLECTION_UUID}/items"

        while True:
            params = {
                "limit": PAGE_SIZE,
                "offset": offset,
                "expand": "metadata,bitstreams",
            }
            self.rate_limiter.wait()
            try:
                resp = self.session.get(url, params=params, timeout=60)
                resp.raise_for_status()
                items = resp.json()
            except Exception as e:
                logger.error("Failed to fetch items at offset %d: %s", offset, e)
                break

            if not items:
                break

            for item in items:
                yield item
                fetched += 1
                if limit and fetched >= limit:
                    return

            offset += len(items)
            if len(items) < PAGE_SIZE:
                break

    def _normalize_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform a DSpace item into the standard LDH schema."""
        metadata = item.get("metadata", [])
        bitstreams = item.get("bitstreams", [])

        title = self._get_metadata_value(metadata, "dc.title") or item.get("name", "")
        if not title:
            return None

        # Extract text: prefer TEXT bitstream, fall back to PDF
        text = self._fetch_text_from_bitstreams(bitstreams)
        if not text:
            text = self._fetch_pdf_text(bitstreams)
        if not text:
            logger.warning("No text available for: %s", title[:80])
            return None

        # Parse date
        date_str = self._get_metadata_value(metadata, "dc.date.issued")
        date_iso = None
        if date_str:
            try:
                if len(date_str) == 4:
                    date_iso = f"{date_str}-01-01"
                elif len(date_str) == 7:
                    date_iso = f"{date_str}-01"
                else:
                    date_iso = date_str[:10]
            except Exception:
                date_iso = None

        # Document type and reference
        doc_type = self._get_metadata_value(metadata, "dc.type") or "Decision"
        reference = self._get_metadata_value(metadata, "au.identifier.reference") or ""
        description = self._get_metadata_value(metadata, "dc.description") or ""
        language = self._get_metadata_value(metadata, "dc.language.iso") or "en"
        authors = self._get_metadata_values(metadata, "dc.contributor.author")

        # Build persistent URL
        handle = item.get("handle", "")
        persistent_url = f"{BASE_URL}/handle/{handle}" if handle else ""
        uri = self._get_metadata_value(metadata, "dc.identifier.uri") or persistent_url

        uuid = item.get("uuid", "")
        _id = f"au-decisions-{uuid}" if uuid else f"au-decisions-{handle.replace('/', '-')}"

        return {
            "_id": _id,
            "_source": "INTL/AU-Decisions",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": uri,
            "doc_type": doc_type,
            "reference": reference,
            "description": description,
            "language": language,
            "authors": authors,
            "handle": handle,
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Yield all Assembly decisions with full text."""
        count = 0
        for item in self._fetch_items():
            record = self._normalize_item(item)
            if record:
                count += 1
                yield record
                if count % 50 == 0:
                    logger.info("Processed %d records", count)
        logger.info("Total records fetched: %d", count)

    def fetch_sample(self, n: int = 15) -> Generator[Dict[str, Any], None, None]:
        """Yield up to n sample records."""
        count = 0
        for item in self._fetch_items(limit=n * 2):
            record = self._normalize_item(item)
            if record:
                count += 1
                yield record
                if count >= n:
                    return
        logger.info("Sample records fetched: %d", count)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch all (DSpace REST API doesn't support date filtering easily)."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Identity transform — normalization happens in _normalize_item."""
        return raw


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/AU-Decisions scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = AUDecisionsScraper()
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command == "test":
        logger.info("Testing connectivity to AU DSpace API...")
        try:
            resp = scraper.session.get(
                f"{REST_BASE}/collections/{ASSEMBLY_COLLECTION_UUID}",
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Connected. Collection: %s (%d items)",
                        data.get("name", "?"), data.get("numberItems", 0))
        except Exception as e:
            logger.error("Connection failed: %s", e)
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample or not args.full:
            logger.info("Fetching sample records...")
            count = 0
            for record in scraper.fetch_sample(15):
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                text_len = len(record.get("text", ""))
                logger.info("[%d] %s (%d chars)", count, record["title"][:60], text_len)
                count += 1
            logger.info("Saved %d sample records to %s", count, sample_dir)
        else:
            logger.info("Fetching all records...")
            count = 0
            for record in scraper.fetch_all():
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                count += 1
            logger.info("Saved %d records", count)
    elif args.command == "update":
        logger.info("Update: fetching all (no incremental support)...")
        count = 0
        for record in scraper.fetch_all():
            count += 1
        logger.info("Fetched %d records", count)


if __name__ == "__main__":
    main()
