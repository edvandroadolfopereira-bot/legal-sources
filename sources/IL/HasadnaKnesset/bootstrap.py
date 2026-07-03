#!/usr/bin/env python3
"""
IL/HasadnaKnesset -- Israeli legislation from Hasadna Open Knesset data pipeline

Fetches Israeli laws from the Hasadna Open Knesset CSV data pipeline at
production.oknesset.org. Joins kns_law (legislation records) with
kns_document_law (PDF document links on fs.knesset.gov.il).
Text extracted from PDFs via pdfplumber.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15+ sample records
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import io
import csv
import json
import logging
import hashlib
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.IL.HasadnaKnesset")

BASE_CSV_URL = "https://production.oknesset.org/pipelines/data/laws"
KNS_LAW_CSV = f"{BASE_CSV_URL}/kns_law/kns_law.csv"
KNS_DOC_CSV = f"{BASE_CSV_URL}/kns_document_law/kns_document_law.csv"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0; +https://github.com/)",
    "Accept": "text/csv, */*",
}


class ILHasadnaKnessetScraper(BaseScraper):
    """Scraper for IL/HasadnaKnesset - Israeli legislation via Hasadna pipeline."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = None
        self._law_map = None
        self._doc_map = None

    def _get_session(self):
        if self.session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            self.session = requests.Session()
            self.session.headers.update(_HEADERS)

            retry_strategy = Retry(
                total=3,
                backoff_factor=2,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        return self.session

    def _download_csv(self, url: str) -> list:
        """Download and parse a CSV file. Returns list of dicts."""
        sess = self._get_session()
        logger.info(f"Downloading CSV: {url}")
        resp = sess.get(url, timeout=120)
        resp.raise_for_status()
        text = resp.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        logger.info(f"  → {len(rows)} rows")
        return rows

    def _load_data(self):
        """Download and index both CSV tables."""
        if self._law_map is not None:
            return

        laws = self._download_csv(KNS_LAW_CSV)
        docs = self._download_csv(KNS_DOC_CSV)

        # Index laws by LawID
        self._law_map = {}
        for law in laws:
            lid = law.get("LawID", "")
            if lid:
                self._law_map[lid] = law

        # Index documents by LawID (only PDF-type documents)
        self._doc_map = defaultdict(list)
        for doc in docs:
            lid = doc.get("LawID", "")
            app = doc.get("ApplicationDesc", "")
            path = doc.get("FilePath", "")
            if lid and path and app == "PDF":
                self._doc_map[lid].append(doc)

        logger.info(f"Loaded {len(self._law_map)} laws, "
                     f"{sum(len(v) for v in self._doc_map.values())} PDF docs "
                     f"for {len(self._doc_map)} laws")

    def _pick_best_pdf(self, docs: list) -> Optional[str]:
        """Pick the best PDF URL from a list of document records.

        Prefers official gazette publications (GroupTypeDesc containing 'פרסום ברשומות')
        then falls back to newest by LastUpdatedDate.
        """
        official = [d for d in docs
                    if "פרסום ברשומות" in d.get("GroupTypeDesc", "")]
        candidates = official if official else docs

        # Sort by LastUpdatedDate descending, pick newest
        def sort_key(d):
            try:
                return d.get("LastUpdatedDate", "")
            except Exception:
                return ""

        candidates.sort(key=sort_key, reverse=True)
        return candidates[0].get("FilePath") if candidates else None

    def _fetch_pdf_bytes(self, url: str) -> Optional[bytes]:
        """Download a PDF. Returns bytes or None on error."""
        self.rate_limiter.wait()
        sess = self._get_session()
        try:
            resp = sess.get(url, timeout=60)
            resp.raise_for_status()
            if len(resp.content) < 200:
                logger.warning(f"PDF too small ({len(resp.content)} bytes): {url}")
                return None
            return resp.content
        except Exception as e:
            logger.warning(f"Failed to download PDF {url}: {e}")
            return None

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        import pdfplumber

        text_parts = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
            return ""
        return "\n\n".join(text_parts)

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all law records that have PDF documents."""
        self._load_data()

        yielded = 0
        for law_id, doc_list in self._doc_map.items():
            law = self._law_map.get(law_id)
            if not law:
                continue

            pdf_url = self._pick_best_pdf(doc_list)
            if not pdf_url:
                continue

            pdf_bytes = self._fetch_pdf_bytes(pdf_url)
            if not pdf_bytes:
                continue

            yielded += 1
            if yielded % 50 == 0:
                logger.info(f"Progress: {yielded} records yielded")

            yield {
                "law_id": law_id,
                "name": law.get("Name", ""),
                "type_desc": law.get("TypeDesc", ""),
                "sub_type_desc": law.get("SubTypeDesc", ""),
                "knesset_num": law.get("KnessetNum", ""),
                "publication_date": law.get("PublicationDate", ""),
                "publication_series": law.get("PublicationSeriesDesc", ""),
                "magazine_number": law.get("MagazineNumber", ""),
                "page_number": law.get("PageNumber", ""),
                "pdf_url": pdf_url,
                "pdf_bytes": pdf_bytes,
            }

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Incremental updates — re-fetch laws updated after the given date."""
        self._load_data()

        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        yielded = 0

        for law_id, doc_list in self._doc_map.items():
            law = self._law_map.get(law_id)
            if not law:
                continue

            last_updated = law.get("LastUpdatedDate", "")
            if last_updated <= since_str:
                continue

            pdf_url = self._pick_best_pdf(doc_list)
            if not pdf_url:
                continue

            pdf_bytes = self._fetch_pdf_bytes(pdf_url)
            if not pdf_bytes:
                continue

            yielded += 1
            yield {
                "law_id": law_id,
                "name": law.get("Name", ""),
                "type_desc": law.get("TypeDesc", ""),
                "sub_type_desc": law.get("SubTypeDesc", ""),
                "knesset_num": law.get("KnessetNum", ""),
                "publication_date": law.get("PublicationDate", ""),
                "publication_series": law.get("PublicationSeriesDesc", ""),
                "magazine_number": law.get("MagazineNumber", ""),
                "page_number": law.get("PageNumber", ""),
                "pdf_url": pdf_url,
                "pdf_bytes": pdf_bytes,
            }

        logger.info(f"Updates: {yielded} records since {since_str}")

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw data into standardized record."""
        pdf_bytes = raw.get("pdf_bytes")
        if not pdf_bytes:
            return None

        text = self._extract_text_from_pdf(pdf_bytes)
        if not text or len(text) < 50:
            logger.warning(f"Insufficient text ({len(text)} chars) from {raw.get('pdf_url', '?')}")
            return None

        law_id = raw.get("law_id", "")
        name = raw.get("name", "")
        pdf_url = raw.get("pdf_url", "")

        # Parse publication date
        pub_date = raw.get("publication_date", "")
        date_str = None
        if pub_date and "T" in pub_date:
            date_str = pub_date.split("T")[0]

        # Stable ID from law_id
        doc_id = f"IL-KNS-{law_id}"

        return {
            "_id": doc_id,
            "_source": "IL/HasadnaKnesset",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": name,
            "text": text,
            "date": date_str,
            "url": pdf_url,
            "law_id": law_id,
            "type_desc": raw.get("type_desc", ""),
            "sub_type_desc": raw.get("sub_type_desc", ""),
            "knesset_num": raw.get("knesset_num", ""),
            "publication_series": raw.get("publication_series", ""),
            "magazine_number": raw.get("magazine_number", ""),
            "page_number": raw.get("page_number", ""),
        }


if __name__ == "__main__":
    scraper = ILHasadnaKnessetScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "test":
        import requests
        try:
            resp = requests.get(KNS_LAW_CSV, headers=_HEADERS, timeout=30, stream=True)
            print(f"kns_law CSV: HTTP {resp.status_code}")
            resp.close()

            resp = requests.get(KNS_DOC_CSV, headers=_HEADERS, timeout=30, stream=True)
            print(f"kns_document_law CSV: HTTP {resp.status_code}")
            resp.close()

            # Test a PDF download
            test_pdf = "https://fs.knesset.gov.il//2/law/2_lsr_311000.PDF"
            resp = requests.head(test_pdf, timeout=15)
            print(f"PDF endpoint: HTTP {resp.status_code}")
            print("Connection OK")
        except Exception as e:
            print(f"Connection FAILED: {e}")
            sys.exit(1)

    elif command == "bootstrap":
        sample_mode = "--sample" in sys.argv
        stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=15)
        print(f"\nBootstrap complete:")
        print(f"  Records fetched: {stats['records_fetched']}")
        if sample_mode:
            print(f"  Sample records saved: {stats.get('sample_records_saved', 0)}")
        else:
            print(f"  New: {stats['records_new']}")
            print(f"  Updated: {stats['records_updated']}")
            print(f"  Skipped: {stats['records_skipped']}")
        print(f"  Errors: {stats['errors']}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
