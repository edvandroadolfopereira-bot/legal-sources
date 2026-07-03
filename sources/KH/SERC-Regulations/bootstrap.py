#!/usr/bin/env python3
"""
KH/SERC-Regulations -- Securities and Exchange Regulator of Cambodia

Fetches laws, anukrets, prakas, and guidelines from the SERC English website.
Documents are PDFs hosted on a PHP board system; text is extracted via pdfplumber.

Board categories:
  - m21laws:     Laws (~4 docs)
  - m22Anukrets: Anukrets / Sub-decrees (~6 docs)
  - m23Prakas:   Prakas / Ministerial Orders (~30 docs, 3 pages)
  - m24guide:    Orders & Guidelines (~7 docs)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.KH.SERC-Regulations")

BOARDS_BASE = "https://www.serc.gov.kh/boards"

# (board_id, category_label, max_pages)
BOARDS = [
    ("m21laws", "laws", 1),
    ("m22Anukrets", "anukrets", 1),
    ("m23Prakas", "prakas", 3),
    ("m24guide", "guidelines", 2),
]


class SERCScraper(BaseScraper):
    """
    Scraper for KH/SERC-Regulations.
    Country: KH
    URL: https://www.serc.gov.kh/english/

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (open-data research project)",
        })

    def _get_listing_page(self, bid: str, page: int = 1) -> list[dict]:
        """Parse one listing page of a board, returning doc metadata."""
        from bs4 import BeautifulSoup

        url = f"{BOARDS_BASE}/index.php?bid={bid}&p={page}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch listing {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        docs = []

        # Document links follow pattern: bid=XXX&nav=read&ntcmode=read&no=YY
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "nav=read" not in href or "ntcmode=read" not in href:
                continue
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            # Extract the no= parameter as document ID
            no_match = re.search(r"no=(\d+)", href)
            if not no_match:
                continue
            doc_no = no_match.group(1)
            docs.append({
                "title": title,
                "doc_no": doc_no,
                "bid": bid,
            })

        return docs

    def _get_pdf_url(self, bid: str, doc_no: str) -> Optional[str]:
        """Fetch a document detail page and extract the PDF download link."""
        from bs4 import BeautifulSoup

        url = f"{BOARDS_BASE}/index.php?bid={bid}&nav=read&ntcmode=read&no={doc_no}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch detail {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ".pdf" in href.lower():
                # Resolve relative URL: ./data_dir/bid/NNNNNN.pdf
                if href.startswith("./"):
                    return f"{BOARDS_BASE}/{href[2:]}"
                elif href.startswith("http"):
                    return href
                else:
                    return f"{BOARDS_BASE}/{href}"
        return None

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download PDF and extract text via pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=90)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {e}")
            return None

        if len(resp.content) < 500:
            return None

        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            pdf.close()
            full_text = "\n\n".join(pages_text)
            return full_text if len(full_text) >= 50 else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return None

    def _get_all_documents(self) -> list[dict]:
        """Collect document metadata from all board categories."""
        all_docs = []
        seen = set()

        for bid, category, max_pages in BOARDS:
            for page in range(1, max_pages + 1):
                docs = self._get_listing_page(bid, page)
                if not docs:
                    break
                for doc in docs:
                    key = (doc["bid"], doc["doc_no"])
                    if key not in seen:
                        seen.add(key)
                        doc["category"] = category
                        all_docs.append(doc)
                time.sleep(1)

        logger.info(f"Found {len(all_docs)} documents across {len(BOARDS)} categories")
        return all_docs

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw document into standard schema."""
        text = raw.get("text", "").strip()
        if not text or len(text) < 50:
            return None

        title = raw.get("title", "").strip()
        if not title:
            return None

        url_hash = hashlib.md5(raw["pdf_url"].encode()).hexdigest()[:12]
        doc_id = f"KH-SERC-{url_hash}"

        return {
            "_id": doc_id,
            "_source": "KH/SERC-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": raw["pdf_url"],
            "category": raw.get("category", ""),
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Fetch all SERC regulatory documents with full PDF text."""
        documents = self._get_all_documents()
        logger.info(f"Processing {len(documents)} documents")

        yielded = 0
        skipped = 0

        for i, doc in enumerate(documents):
            if (i + 1) % 10 == 0:
                logger.info(f"[{i+1}/{len(documents)}] Yielded: {yielded}, Skipped: {skipped}")

            pdf_url = self._get_pdf_url(doc["bid"], doc["doc_no"])
            if not pdf_url:
                logger.warning(f"No PDF found for: {doc['title'][:60]}")
                skipped += 1
                continue

            doc["pdf_url"] = pdf_url

            text = self._extract_pdf_text(pdf_url)
            if not text:
                skipped += 1
                continue

            doc["text"] = text
            normalized = self.normalize(doc)
            if normalized:
                yielded += 1
                yield normalized

            time.sleep(1.5)

        logger.info(f"Done. Yielded: {yielded}, Skipped: {skipped}")

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """Fetch recently added documents (no date-sorted API, re-fetch all)."""
        yield from self.fetch_all()

    def test(self) -> dict:
        """Quick connectivity test."""
        url = f"{BOARDS_BASE}/index.php?bid=m23Prakas"
        resp = self.session.get(url, timeout=30)
        return {
            "status": "ok" if resp.status_code == 200 else "error",
            "http_code": resp.status_code,
            "url": url,
        }


if __name__ == "__main__":
    scraper = SERCScraper()

    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test":
        result = scraper.test()
        print(json.dumps(result, indent=2))
    elif command in ("bootstrap", "bootstrap-fast", "update"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        jsonl_path = data_dir / "records.jsonl"

        count = 0
        limit = 15 if sample_mode else 99999

        gen = scraper.fetch_all() if command != "update" else scraper.fetch_updates()

        # In non-sample mode, stream every record to data/records.jsonl so the
        # VPS ingest pipeline (which reads records.jsonl) persists the full set.
        # Previously these were only printed to stdout → 0 records ingested.
        jsonl_fh = None if sample_mode else jsonl_path.open("w", encoding="utf-8")
        try:
            for record in gen:
                count += 1
                if sample_mode:
                    outpath = sample_dir / f"{count:04d}.json"
                    outpath.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                    print(f"[{count}] {record['title'][:60]} ({len(record['text'])} chars)")
                else:
                    jsonl_fh.write(json.dumps(record, ensure_ascii=False) + "\n")

                if count >= limit:
                    break
        finally:
            if jsonl_fh is not None:
                jsonl_fh.close()

        print(f"\nTotal records: {count}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
