#!/usr/bin/env python3
"""
GY/EPA-Regulations — Guyana Environmental Protection Agency

Fetches environmental regulations, guidelines, EIA guidelines, and policies
from the EPA Guyana website via the WordPress REST API.

Strategy:
  1. Query WP REST API for wpdmpro posts in regulatory categories
  2. Download each PDF via ?wpdmdl=<id> URL
  3. Extract text with pdfminer
  4. Normalize into standard schema

Usage:
  python bootstrap.py bootstrap           # Full initial pull
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py bootstrap-fast      # Alias for bootstrap
  python bootstrap.py update              # Incremental (re-fetches all)
  python bootstrap.py test-api            # Quick connectivity test
"""

import io
import re
import sys
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from html import unescape

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GY.EPA-Regulations")

BASE_URL = "https://epaguyana.org"
SOURCE_ID = "GY/EPA-Regulations"

# WPDM category IDs for regulatory/legal content
CATEGORY_IDS = {
    18: "Regulations",
    19: "Guidelines",
    31: "EIA Guidelines",
    44: "Policies and Plans",
    35: "Strategies and Action Plans",
    34: "MEA Reports",
}


def _extract_text_pdfminer(pdf_bytes: bytes) -> Optional[str]:
    """Extract text from PDF bytes using pdfminer."""
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(io.BytesIO(pdf_bytes))
        if text and len(text.strip()) > 50:
            return text.strip()
    except Exception as e:
        logger.warning("pdfminer extraction failed: %s", e)
    return None


def _clean_html_title(raw: str) -> str:
    """Decode HTML entities and strip tags from a title."""
    text = re.sub(r"<[^>]+>", "", raw)
    return unescape(text).strip()


class EPARegulationsScraper(BaseScraper):

    def __init__(self):
        super().__init__(str(Path(__file__).parent))
        self.http = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (open legal data research)",
                "Accept": "application/json, application/pdf, */*",
            },
            timeout=60,
        )

    def _list_documents(self) -> list[dict]:
        """Query WP REST API for wpdmpro posts in regulatory categories."""
        all_docs = []
        seen_ids = set()

        for cat_id, cat_name in CATEGORY_IDS.items():
            page = 1
            while True:
                url = (
                    f"{BASE_URL}/wp-json/wp/v2/wpdmpro"
                    f"?wpdmcategory={cat_id}&per_page=100&page={page}"
                )
                logger.info("Fetching %s page %d", cat_name, page)
                resp = self.http.get(url, timeout=60)
                if resp.status_code != 200:
                    logger.warning(
                        "API returned %d for %s page %d",
                        resp.status_code, cat_name, page,
                    )
                    break

                items = resp.json()
                if not items:
                    break

                for item in items:
                    doc_id = item["id"]
                    if doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)
                    all_docs.append({
                        "wp_id": doc_id,
                        "title": _clean_html_title(
                            item.get("title", {}).get("rendered", "")
                        ),
                        "slug": item.get("slug", ""),
                        "link": item.get("link", ""),
                        "date": item.get("date", ""),
                        "modified": item.get("modified", ""),
                        "category": cat_name,
                    })

                total_pages = int(
                    resp.headers.get("X-WP-TotalPages", "1")
                )
                if page >= total_pages:
                    break
                page += 1
                time.sleep(0.5)

        logger.info("Total documents found: %d", len(all_docs))
        return all_docs

    def _download_pdf(self, doc: dict) -> Optional[bytes]:
        """Download a PDF from WPDM using the wpdmdl parameter."""
        download_url = f"{doc['link']}?wpdmdl={doc['wp_id']}&refresh=ldh"
        try:
            resp = self.http.get(download_url, timeout=90)
            if resp.status_code != 200:
                logger.warning(
                    "PDF download failed (%d): %s",
                    resp.status_code, doc["title"],
                )
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                logger.warning(
                    "Not a PDF (%s): %s", content_type, doc["title"]
                )
                return None
            return resp.content
        except Exception as e:
            logger.warning(
                "PDF download error for %s: %s", doc["title"], e
            )
            return None

    def _normalize_record(self, doc: dict) -> Optional[dict]:
        """Download PDF, extract text, and build normalized record."""
        pdf_bytes = self._download_pdf(doc)
        if not pdf_bytes:
            return None

        text = _extract_text_pdfminer(pdf_bytes)
        if not text:
            logger.warning("No text extracted: %s", doc["title"])
            return None

        # Parse date from WP API response
        date_str = None
        if doc.get("date"):
            try:
                dt = datetime.fromisoformat(doc["date"])
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        doc_id = f"epa-{doc['wp_id']}-{doc['slug']}"

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": doc["title"],
            "text": text,
            "date": date_str,
            "url": doc["link"],
            "category": doc["category"],
            "wp_id": doc["wp_id"],
        }

    # ── BaseScraper interface ────────────────────────────────────────

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all EPA regulatory documents."""
        docs = self._list_documents()
        for doc in docs:
            record = self._normalize_record(doc)
            if record:
                yield record
            time.sleep(1)

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """No date-based filtering — re-fetches all."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Pass-through — normalization is done in fetch methods."""
        return raw


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="GY/EPA-Regulations scraper")
    parser.add_argument(
        "command", choices=["bootstrap", "bootstrap-fast", "update", "test-api"]
    )
    parser.add_argument(
        "--sample", action="store_true", help="Fetch only sample records"
    )
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = EPARegulationsScraper()

    if args.command == "test-api":
        docs = scraper._list_documents()
        for cat_name in CATEGORY_IDS.values():
            cat_docs = [d for d in docs if d["category"] == cat_name]
            logger.info("%s: %d documents", cat_name, len(cat_docs))
            if cat_docs:
                logger.info("  Sample: %s", cat_docs[0]["title"][:80])
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command in ("bootstrap", "bootstrap-fast", "update"):
        limit = 15 if args.sample else None
        count = 0
        for record in scraper.fetch_all():
            count += 1
            if args.sample or count <= 15:
                out_path = sample_dir / f"{count:04d}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
            logger.info(
                "[%d] %s — %d chars",
                count,
                record["title"][:60],
                len(record.get("text", "")),
            )
            if limit and count >= limit:
                break

        logger.info("Done: %d records fetched", count)


if __name__ == "__main__":
    main()
