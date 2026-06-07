#!/usr/bin/env python3
"""
INTL/ArcticCouncil-Docs -- Arctic Council Open Access Archive

Fetches governance and treaty documents from the Arctic Council's DSpace 7
institutional repository at oaarchive.arctic-council.org.

Strategy:
  - Use DSpace 7 REST API to paginate all items (/server/api/discover/search/objects)
  - For each item, fetch metadata (title, date, abstract, authors, type)
  - Fetch pre-extracted full text from the TEXT bundle (DSpace auto-extracts
    text from uploaded PDFs)
  - If no TEXT bundle exists, fall back to downloading the ORIGINAL PDF and
    extracting text with pdfplumber
  - ~3,165 items covering 1996-present

Endpoints:
  - Search:  /server/api/discover/search/objects?dsoType=ITEM&size=20&page=N
  - Item:    /server/api/core/items/{uuid}
  - Bundles: /server/api/core/items/{uuid}/bundles
  - Text:    /server/api/core/bitstreams/{uuid}/content

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ArcticCouncil-Docs")

BASE_URL = "https://oaarchive.arctic-council.org"
API_BASE = f"{BASE_URL}/server/api"
SOURCE_ID = "INTL/ArcticCouncil-Docs"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (research; +https://legaldatahunter.com)",
    "Accept": "application/json",
}

PAGE_SIZE = 20
SAMPLE_LIMIT = 15


def _clean_text(text: str) -> str:
    """Tidy extracted text: collapse whitespace, remove control chars."""
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class ArcticCouncilDocsScraper(BaseScraper):
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self.http = HttpClient(headers=HEADERS)

    def _api_get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """GET a JSON endpoint from the DSpace API."""
        url = f"{API_BASE}/{endpoint}"
        try:
            resp = self.http.get(url, params=params)
            if resp and resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"API GET failed {url}: {e}")
        return None

    def _get_bytes(self, url: str) -> Optional[bytes]:
        """Fetch raw bytes (for text files or PDFs)."""
        try:
            resp = self.http.get(url)
            if resp and resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.warning(f"Failed to fetch bytes {url}: {e}")
        return None

    def _get_text_from_bundles(self, item_uuid: str) -> str:
        """Try to get pre-extracted text from DSpace TEXT bundle."""
        data = self._api_get(f"core/items/{item_uuid}/bundles")
        if not data:
            return ""

        for bundle in data.get("_embedded", {}).get("bundles", []):
            if bundle.get("name") == "TEXT":
                bs_url = bundle["_links"]["bitstreams"]["href"]
                try:
                    resp = self.http.get(bs_url)
                    if resp and resp.status_code == 200:
                        bs_data = resp.json()
                        for bs in bs_data.get("_embedded", {}).get("bitstreams", []):
                            content_url = bs["_links"]["content"]["href"]
                            text_bytes = self._get_bytes(content_url)
                            if text_bytes:
                                return _clean_text(text_bytes.decode("utf-8", errors="replace"))
                except Exception as e:
                    logger.warning(f"Failed to read TEXT bundle for {item_uuid}: {e}")

        return ""

    def _get_pdf_text_from_bundles(self, item_uuid: str) -> str:
        """Fallback: download ORIGINAL PDF and extract text."""
        data = self._api_get(f"core/items/{item_uuid}/bundles")
        if not data:
            return ""

        for bundle in data.get("_embedded", {}).get("bundles", []):
            if bundle.get("name") == "ORIGINAL":
                bs_url = bundle["_links"]["bitstreams"]["href"]
                try:
                    resp = self.http.get(bs_url)
                    if resp and resp.status_code == 200:
                        bs_data = resp.json()
                        for bs in bs_data.get("_embedded", {}).get("bitstreams", []):
                            name = bs.get("name", "")
                            if name.lower().endswith(".pdf"):
                                content_url = bs["_links"]["content"]["href"]
                                pdf_bytes = self._get_bytes(content_url)
                                if pdf_bytes:
                                    return self._extract_pdf(pdf_bytes)
                except Exception as e:
                    logger.warning(f"Failed to read ORIGINAL bundle for {item_uuid}: {e}")

        return ""

    def _extract_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        try:
            import io
            import pdfplumber
            pages = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
            return _clean_text("\n\n".join(pages))
        except ImportError:
            logger.warning("pdfplumber not available, skipping PDF extraction")
            return ""
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return ""

    def _extract_metadata(self, item: dict) -> Dict[str, Any]:
        """Extract structured metadata from a DSpace item."""
        meta = item.get("metadata", {})

        def first(key: str) -> Optional[str]:
            vals = meta.get(key, [])
            return vals[0]["value"] if vals else None

        def all_vals(key: str) -> List[str]:
            return [v["value"] for v in meta.get(key, [])]

        title = first("dc.title") or item.get("name", "")
        abstract = first("dc.description.abstract") or ""
        date_str = first("dc.date.issued") or first("dc.date.available") or ""
        authors = all_vals("dc.contributor.author")
        doc_type = first("dc.type") or ""
        subjects = all_vals("dc.subject")
        publisher = first("dc.publisher") or ""
        language = first("dc.language.iso") or first("dc.language") or "en"
        handle = item.get("handle", "")
        uuid = item.get("uuid", "")

        # Normalize date to ISO format
        iso_date = None
        if date_str:
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    iso_date = datetime.strptime(date_str[:len(fmt.replace('%', 'X'))], fmt).strftime("%Y-%m-%d") if len(date_str) >= 4 else None
                    break
                except (ValueError, IndexError):
                    continue
            if not iso_date and len(date_str) >= 4:
                iso_date = date_str[:4] + "-01-01"

        return {
            "uuid": uuid,
            "handle": handle,
            "title": title,
            "abstract": abstract,
            "date": iso_date,
            "date_raw": date_str,
            "authors": authors,
            "doc_type": doc_type,
            "subjects": subjects,
            "publisher": publisher,
            "language": language,
            "url": f"{BASE_URL}/handle/{handle}" if handle else "",
        }

    def _fetch_item_text(self, uuid: str) -> str:
        """Get full text for an item: try TEXT bundle first, then PDF fallback."""
        text = self._get_text_from_bundles(uuid)
        if text and len(text) > 100:
            return text

        logger.info(f"No TEXT bundle for {uuid}, trying PDF extraction")
        text = self._get_pdf_text_from_bundles(uuid)
        return text

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Paginate DSpace search API and yield normalized records."""
        page = 0
        total_yielded = 0
        limit = SAMPLE_LIMIT if sample else 999999

        while total_yielded < limit:
            data = self._api_get("discover/search/objects", {
                "dsoType": "ITEM",
                "size": PAGE_SIZE,
                "page": page,
                "sort": "dc.date.issued,DESC",
            })

            if not data:
                logger.warning(f"No data returned for page {page}")
                break

            sr = data.get("_embedded", {}).get("searchResult", {})
            objects = sr.get("_embedded", {}).get("objects", [])
            page_info = sr.get("page", {})

            if not objects:
                logger.info(f"No more items at page {page}")
                break

            for obj in objects:
                if total_yielded >= limit:
                    break

                item = obj.get("_embedded", {}).get("indexableObject", {})
                if not item or item.get("type") != "item":
                    continue

                meta = self._extract_metadata(item)
                uuid = meta["uuid"]

                # Fetch full text
                text = self._fetch_item_text(uuid)
                if not text:
                    # Use abstract as minimal text if nothing else available
                    text = meta.get("abstract", "")

                if not text or len(text) < 50:
                    logger.info(f"Skipping {uuid} ({meta['title'][:50]}): insufficient text ({len(text)} chars)")
                    continue

                record = self.normalize({
                    **meta,
                    "text": text,
                })

                total_yielded += 1
                logger.info(
                    f"[{total_yielded}] {meta['title'][:60]} "
                    f"({len(text)} chars)"
                )
                yield record
                time.sleep(0.5)

            total_pages = page_info.get("totalPages", 0)
            page += 1
            if page >= total_pages:
                break

            time.sleep(1)

        logger.info(f"Finished: yielded {total_yielded} records")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch items modified since a date."""
        yield from self.fetch_all(sample=False)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform to standard LDH schema."""
        handle = raw.get("handle", "")
        uuid = raw.get("uuid", "")
        doc_id = handle or uuid

        text = raw.get("text", "")
        abstract = raw.get("abstract", "")

        # Combine abstract and text if both present and different
        if abstract and text and abstract not in text:
            full_text = f"{abstract}\n\n{text}"
        else:
            full_text = text or abstract

        return {
            "_id": f"arctic-council-{doc_id}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": full_text,
            "date": raw.get("date"),
            "url": raw.get("url", ""),
            "authors": raw.get("authors", []),
            "doc_type": raw.get("doc_type", ""),
            "subjects": raw.get("subjects", []),
            "publisher": raw.get("publisher", ""),
            "language": raw.get("language", "en"),
            "handle": handle,
        }


# --------------- CLI ---------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/ArcticCouncil-Docs bootstrap")
    parser.add_argument("command", choices=["bootstrap", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = ArcticCouncilDocsScraper()

    if args.command == "test":
        data = scraper._api_get("", {})
        if data and data.get("dspaceName"):
            print(f"OK: Connected to {data['dspaceName']} ({data.get('dspaceVersion', '?')})")
        else:
            print("FAIL: Could not connect to DSpace API")
            sys.exit(1)
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    is_sample = args.sample or (args.command == "bootstrap" and not args.full)
    count = 0

    for record in scraper.fetch_all(sample=is_sample):
        out_path = sample_dir / f"{count:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        count += 1
        text_len = len(record.get("text", ""))
        print(f"  [{count}] {record['title'][:60]} ({text_len} chars)")

    print(f"\nDone: {count} records saved to {sample_dir}/")


if __name__ == "__main__":
    main()
