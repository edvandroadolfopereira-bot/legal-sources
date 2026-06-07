#!/usr/bin/env python3
"""
SR/SRiS -- Suriname Rechtsinformatie Systeem (Legal Information System)

Fetches ~1,300+ Surinamese legal documents from sris.sr via the WordPress
REST API media endpoint. Documents include legislation (Staatsblad), draft
bills (Ontwerpwetten), Constitutional Court decisions, resolutions, and
government decrees — all published as PDFs.

Strategy:
  - Paginate WP REST API /wp-json/wp/v2/media?media_type=application
  - Download each PDF and extract text via pypdf
  - Classify by title patterns (legislation, case_law, doctrine)

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py bootstrap-fast --sample
  python bootstrap.py test
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SR.SRiS")

API_BASE = "https://www.sris.sr/wp-json/wp/v2"
MEDIA_ENDPOINT = f"{API_BASE}/media"

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
    logger.warning("pypdf not installed; PDF text extraction unavailable")

# Title patterns for classification
CASE_LAW_PATTERNS = re.compile(
    r"(Constitutioneel\s+Hof|CH[-\s]*\d|Uitspraak|Beschikkingen\s+strafzaken|"
    r"Krijgsraad|vonnis|arrest)",
    re.IGNORECASE,
)
DOCTRINE_PATTERNS = re.compile(
    r"(thesis|scriptie|uiteenzetting|cursus|aanmelding|^artikelen\b)",
    re.IGNORECASE,
)


class SRiSScraper(BaseScraper):
    """Scraper for SR/SRiS — Suriname Legal Information System."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def _request(self, url: str, timeout: int = 60, **kwargs) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(1.5)
                resp = self.session.get(url, timeout=timeout, **kwargs)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 30s")
                    time.sleep(30)
                    continue
                if resp.status_code == 400:
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text).strip()
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            return full_text
        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
            return ""

    def _classify_doc(self, title: str) -> str:
        if CASE_LAW_PATTERNS.search(title):
            return "case_law"
        if DOCTRINE_PATTERNS.search(title):
            return "doctrine"
        return "legislation"

    def _extract_date(self, wp_date: str) -> str:
        """Extract ISO date from WP date string."""
        if wp_date:
            return wp_date[:10]
        return ""

    def _extract_sb_ref(self, title: str) -> str:
        """Extract Staatsblad reference (e.g. S.B. 2024 no. 74) from title."""
        m = re.search(r"S\.B\.\s*\d{4}\s*no\.\s*\d+", title, re.IGNORECASE)
        if m:
            return m.group(0)
        m = re.search(r"G\.B\.\s*\d{4}\s*no\.\s*\d+", title, re.IGNORECASE)
        if m:
            return m.group(0)
        return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw.get("doc_id", ""),
            "_source": "SR/SRiS",
            "_type": raw.get("doc_type", "legislation"),
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "pdf_url": raw.get("pdf_url", ""),
            "sb_reference": raw.get("sb_reference", ""),
            "doc_type": raw.get("doc_type", "legislation"),
        }

    def _iter_media(self) -> Generator[Dict[str, Any], None, None]:
        """Paginate through all PDF media items via WP REST API."""
        page = 1
        per_page = 100
        while True:
            url = f"{MEDIA_ENDPOINT}?media_type=application&per_page={per_page}&page={page}"
            resp = self._request(url)
            if resp is None:
                break
            try:
                items = resp.json()
            except Exception:
                break
            if not items:
                break
            for item in items:
                yield item
            if len(items) < per_page:
                break
            page += 1

    def fetch_all(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        count = 0
        skipped = 0

        for item in self._iter_media():
            if max_records and count >= max_records:
                return

            media_id = item.get("id", 0)
            title = item.get("title", {}).get("rendered", "").strip()
            source_url = item.get("source_url", "")
            wp_date = item.get("date", "")
            mime_type = item.get("mime_type", "")

            if not source_url or not source_url.lower().endswith(".pdf"):
                skipped += 1
                continue

            if not title:
                title = source_url.split("/")[-1].replace(".pdf", "").replace("-", " ")

            # Download PDF
            resp = self._request(source_url, timeout=120)
            if resp is None:
                logger.warning(f"Failed to download: {title}")
                skipped += 1
                continue

            if len(resp.content) > 50 * 1024 * 1024:
                logger.warning(f"PDF too large ({len(resp.content)} bytes): {title}")
                skipped += 1
                continue

            text = self._extract_pdf_text(resp.content)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text ({len(text)} chars): {title}")
                skipped += 1
                continue

            doc_type = self._classify_doc(title)
            date = self._extract_date(wp_date)
            sb_ref = self._extract_sb_ref(title)
            doc_id = f"SR-SRiS-{media_id}"

            raw = {
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "date": date,
                "url": item.get("link", source_url),
                "pdf_url": source_url,
                "doc_type": doc_type,
                "sb_reference": sb_ref,
            }
            count += 1
            yield raw

        logger.info(f"Completed: {count} documents fetched, {skipped} skipped")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(max_records=20)

    def test(self) -> bool:
        resp = self._request(f"{MEDIA_ENDPOINT}?media_type=application&per_page=1")
        if resp is None:
            logger.error("Cannot reach WP REST API")
            return False

        items = resp.json()
        if not items:
            logger.error("No media items returned")
            return False

        total = resp.headers.get("X-WP-Total", "?")
        logger.info(f"API OK: {total} total media items")

        item = items[0]
        pdf_url = item.get("source_url", "")
        if pdf_url and pdf_url.lower().endswith(".pdf"):
            pdf_resp = self._request(pdf_url, timeout=120)
            if pdf_resp:
                text = self._extract_pdf_text(pdf_resp.content)
                logger.info(f"PDF OK: {item['title']['rendered'][:60]} ({len(text)} chars)")
            else:
                logger.warning("Could not download sample PDF")
        return True


def main():
    parser = argparse.ArgumentParser(description="SR/SRiS data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = SRiSScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else None

        for record in scraper.fetch_all(max_records=max_records):
            normalized = scraper.normalize(record)
            out_path = sample_dir / f"record_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            text_len = len(normalized.get("text", ""))
            logger.info(
                f"[{count + 1}] {normalized.get('title', '?')[:80]} "
                f"({text_len:,} chars)"
            )
            count += 1

        logger.info(f"Bootstrap complete: {count} records saved to sample/")

    elif args.command == "update":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for record in scraper.fetch_updates():
            normalized = scraper.normalize(record)
            out_path = sample_dir / f"update_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            count += 1
        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
