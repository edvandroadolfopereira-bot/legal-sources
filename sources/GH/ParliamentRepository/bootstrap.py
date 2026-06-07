#!/usr/bin/env python3
"""
GH/ParliamentRepository -- Ghana Parliament Institutional Repository

Fetches all parliamentary materials from the official Parliament of Ghana
DSpace 9 institutional repository via REST API.

Covers: bills, official reports (Hansard), committee reports,
constitutional/executive/legislative instruments, decrees, budget estimates,
agreements, conventions, and more (~3,900+ items).

Strategy:
  - Global search across entire repository (no community scope)
  - Paginate through all items via discover/search endpoint
  - Fetch item metadata + full text from TEXT bundle bitstreams
  - DSpace pre-extracts text from PDFs — no PDF parsing needed
  - Uses curl subprocess for HTTPS (system Python SSL compatibility)

Usage:
  python bootstrap.py bootstrap          # Fetch all records
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Same as bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GH.ParliamentRepository")

API_BASE = "https://repository.parliament.gh/server/api"
REPO_BASE = "https://repository.parliament.gh"
PAGE_SIZE = 20


def _curl_get(url: str, accept: str = "application/json", timeout: int = 30) -> Optional[str]:
    """HTTP GET via curl subprocess (bypasses Python SSL limitations)."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-f",
                "--max-time", str(timeout),
                "-H", f"Accept: {accept}",
                "-H", "User-Agent: Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"curl failed for {url[:100]}: {e}")
        return None


def _curl_json(url: str, timeout: int = 30) -> Optional[Dict]:
    """Fetch JSON from URL via curl."""
    body = _curl_get(url, accept="application/json", timeout=timeout)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode error: {e}")
        return None


class ParliamentRepositoryScraper(BaseScraper):
    """Scraper for GH/ParliamentRepository -- full Ghana Parliament DSpace repository."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def _api_get(self, url: str) -> Optional[Dict]:
        """GET request to DSpace API with retry and rate limiting."""
        for attempt in range(3):
            time.sleep(1)
            data = _curl_json(url)
            if data is not None:
                return data
            logger.warning(f"Attempt {attempt+1} failed for {url[:100]}")
            if attempt < 2:
                time.sleep(5)
        return None

    def _fetch_text(self, url: str) -> Optional[str]:
        """GET plain text content (bitstream)."""
        for attempt in range(3):
            time.sleep(1)
            body = _curl_get(url, accept="text/plain, */*")
            if body is not None:
                return body
            logger.warning(f"Text fetch attempt {attempt+1} failed")
            if attempt < 2:
                time.sleep(5)
        return None

    def _get_text_bitstream_url(self, item_uuid: str) -> Optional[str]:
        """Find the TEXT bundle bitstream content URL for an item."""
        bundles_url = f"{API_BASE}/core/items/{item_uuid}/bundles"
        data = self._api_get(bundles_url)
        if not data:
            return None

        bundles = data.get("_embedded", {}).get("bundles", [])
        text_bundle = None
        for b in bundles:
            if b.get("name") == "TEXT":
                text_bundle = b
                break

        if not text_bundle:
            return None

        bs_url = text_bundle.get("_links", {}).get("bitstreams", {}).get("href")
        if not bs_url:
            return None

        bs_data = self._api_get(bs_url)
        if not bs_data:
            return None

        bitstreams = bs_data.get("_embedded", {}).get("bitstreams", [])
        if not bitstreams:
            return None

        return bitstreams[0].get("_links", {}).get("content", {}).get("href")

    def _extract_metadata(self, item: Dict) -> Dict[str, str]:
        """Extract metadata fields from a DSpace item object."""
        meta = item.get("metadata", {})

        def get_val(key: str) -> str:
            vals = meta.get(key, [])
            return vals[0].get("value", "") if vals else ""

        def get_all_vals(key: str) -> str:
            vals = meta.get(key, [])
            return "; ".join(v.get("value", "") for v in vals if v.get("value"))

        title = get_val("dc.title")
        date_issued = get_val("dc.date.issued")
        uri = get_val("dc.identifier.uri")
        author = get_val("dc.contributor.author")
        subject = get_all_vals("dc.subject")
        publisher = get_val("dc.publisher")
        language = get_val("dc.language.iso")
        doc_type = get_val("dc.type")
        abstract = get_val("dc.description.abstract")
        description = get_val("dc.description")

        return {
            "uuid": item.get("uuid", ""),
            "title": title,
            "date": date_issued,
            "uri": uri,
            "author": author,
            "subject": subject,
            "publisher": publisher,
            "language": language or "en",
            "handle": item.get("handle", ""),
            "doc_type": doc_type,
            "abstract": abstract,
            "description": description,
        }

    def _search_all_items(self, max_pages: int = 250) -> Generator[Dict, None, None]:
        """Iterate all items in the repository via global discover search."""
        page = 0
        while page < max_pages:
            url = (
                f"{API_BASE}/discover/search/objects"
                f"?dsoType=ITEM&size={PAGE_SIZE}&page={page}"
                f"&sort=dc.date.accessioned,DESC"
            )
            data = self._api_get(url)
            if not data:
                break

            search_result = data.get("_embedded", {}).get("searchResult", {})
            objects = search_result.get("_embedded", {}).get("objects", [])
            if not objects:
                break

            for obj in objects:
                item = obj.get("_embedded", {}).get("indexableObject", {})
                if item:
                    yield item

            page_info = search_result.get("page", {})
            total_pages = page_info.get("totalPages", 0)
            if page + 1 >= total_pages:
                break
            page += 1

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        uuid = raw.get("uuid", "")
        date = raw.get("date", "")
        if date and re.match(r"^\d{4}$", date):
            date = f"{date}-01-01"

        handle = raw.get("handle", "")
        url = raw.get("uri", "")
        if not url and handle:
            url = f"{REPO_BASE}/handle/{handle}"

        return {
            "_id": f"GH-PARLREPO-{uuid}",
            "_source": "GH/ParliamentRepository",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": date,
            "url": url,
            "author": raw.get("author", ""),
            "subject": raw.get("subject", ""),
            "doc_type": raw.get("doc_type", ""),
            "language": raw.get("language", "en"),
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all items from the entire repository."""
        count = 0
        skipped = 0
        seen_uuids = set()

        for item in self._search_all_items():
            uuid = item.get("uuid", "")
            if uuid in seen_uuids:
                continue
            seen_uuids.add(uuid)

            metadata = self._extract_metadata(item)

            text_url = self._get_text_bitstream_url(uuid)
            if not text_url:
                skipped += 1
                logger.debug(f"No TEXT bundle: {metadata['title'][:60]}")
                continue

            text = self._fetch_text(text_url)
            if not text or len(text.strip()) < 50:
                skipped += 1
                logger.debug(f"Insufficient text: {metadata['title'][:60]}")
                continue

            text = re.sub(r"\r\n", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()

            raw = {**metadata, "text": text}
            count += 1
            yield raw

            if count % 100 == 0:
                logger.info(f"Progress: {count} records fetched, {skipped} skipped")

        logger.info(f"Completed: {count} total records fetched, {skipped} skipped (no text)")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        """Fetch most recently added items."""
        count = 0
        url = (
            f"{API_BASE}/discover/search/objects"
            f"?dsoType=ITEM&size=20&page=0"
            f"&sort=dc.date.accessioned,DESC"
        )
        data = self._api_get(url)
        if not data:
            return

        objects = (
            data.get("_embedded", {})
            .get("searchResult", {})
            .get("_embedded", {})
            .get("objects", [])
        )

        for obj in objects:
            item = obj.get("_embedded", {}).get("indexableObject", {})
            if not item:
                continue

            uuid = item.get("uuid", "")
            metadata = self._extract_metadata(item)

            text_url = self._get_text_bitstream_url(uuid)
            if not text_url:
                continue

            text = self._fetch_text(text_url)
            if not text or len(text.strip()) < 50:
                continue

            text = re.sub(r"\r\n", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()

            raw = {**metadata, "text": text}
            count += 1
            yield raw

        logger.info(f"Updates: {count} records fetched")

    def test(self) -> bool:
        """Quick connectivity test."""
        url = f"{API_BASE}/core/communities?size=1"
        data = self._api_get(url)
        if not data:
            logger.error("Cannot reach DSpace API")
            return False

        communities = data.get("_embedded", {}).get("communities", [])
        if communities:
            logger.info(f"API OK: community '{communities[0].get('name', 'N/A')}'")

        search_url = (
            f"{API_BASE}/discover/search/objects"
            f"?dsoType=ITEM&size=1&sort=dc.date.accessioned,DESC"
        )
        search_data = self._api_get(search_url)
        if not search_data:
            logger.error("Search endpoint failed")
            return False

        page_info = (
            search_data.get("_embedded", {})
            .get("searchResult", {})
            .get("page", {})
        )
        logger.info(f"Total items: {page_info.get('totalElements', 'unknown')}")

        objects = (
            search_data.get("_embedded", {})
            .get("searchResult", {})
            .get("_embedded", {})
            .get("objects", [])
        )
        if not objects:
            logger.error("No items found")
            return False

        item = objects[0].get("_embedded", {}).get("indexableObject", {})
        meta = self._extract_metadata(item)
        logger.info(f"Item OK: {meta['title'][:60]}")

        text_url = self._get_text_bitstream_url(meta["uuid"])
        if text_url:
            text = self._fetch_text(text_url)
            if text and len(text.strip()) > 50:
                logger.info(f"Text OK: {len(text)} chars")
            else:
                logger.warning("Text fetch returned empty or short content")
        else:
            logger.warning("No TEXT bundle found for test item")

        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GH/ParliamentRepository data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Only fetch a small sample (for validation)",
    )
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = ParliamentRepositoryScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command in ("bootstrap", "bootstrap-fast"):
        stats = scraper.bootstrap(sample_mode=args.sample, sample_size=15)
        fetched = stats.get("records_fetched", 0) or stats.get("sample_records_saved", 0)
        logger.info(f"Bootstrap complete: {fetched} records — {stats}")
        if fetched == 0:
            sys.exit(1)

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {stats}")


if __name__ == "__main__":
    main()
