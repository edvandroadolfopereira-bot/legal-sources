#!/usr/bin/env python3
"""
INTL/GCC-LegalDocs -- Gulf Cooperation Council Digital Library

Fetches official GCC legal instruments from the Secretariat's digital library.

Strategy:
  - Parse the SharePoint digital library pages (paginated, 30 per page)
  - Extract metadata (title, year, topic, language) from the HTML table rows
  - Download each PDF and extract full text with pdfplumber
  - ~64 documents covering economic agreements, unified regulations, etc.

Endpoints:
  - Library: https://www.gcc-sg.org/en/MediaCenter/DigitalLibrary/Pages/default.aspx
  - PDFs:    https://www.gcc-sg.org/en/MediaCenter/DigitalLibrary/Documents/{id}.pdf

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
import io
import time
import hashlib
import html as html_mod
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
logger = logging.getLogger("legal-data-hunter.INTL.GCC-LegalDocs")

BASE_URL = "https://www.gcc-sg.org"
LIBRARY_URL = f"{BASE_URL}/en/MediaCenter/DigitalLibrary/Pages/default.aspx"
SOURCE_ID = "INTL/GCC-LegalDocs"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (research; +https://legaldatahunter.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SAMPLE_LIMIT = 15
MAX_PAGES = 10  # safety limit


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s).strip()
    return html_mod.unescape(s)


def _parse_year(raw: str) -> Optional[str]:
    """Parse year from SharePoint field like '2,014' or '2014'."""
    raw = raw.replace(",", "").strip()
    m = re.search(r"(19|20)\d{2}", raw)
    if m:
        return m.group(0)
    return None


class GCCLegalDocsScraper(BaseScraper):
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        super().__init__()
        self.http = HttpClient(headers=HEADERS)

    def _get(self, url: str) -> Optional[str]:
        try:
            resp = self.http.get(url)
            if resp and resp.status_code == 200:
                return resp.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
        return None

    def _get_bytes(self, url: str) -> Optional[bytes]:
        try:
            resp = self.http.get(url)
            if resp and resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.warning(f"Failed to fetch bytes {url}: {e}")
        return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
            return _clean_text("\n\n".join(pages))
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return ""

    def _parse_library_page(self, html: str) -> List[Dict[str, str]]:
        """Parse one page of the GCC digital library for documents with metadata."""
        docs = []
        seen_urls = set()

        # Find all table rows (each document is a tr with class ms-itmhover or similar)
        # The structure has 18 columns per row
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

        for row_html in rows:
            # Check if this row contains a PDF link
            pdf_match = re.search(
                r'href="(https://www\.gcc-sg\.org/en/MediaCenter/DigitalLibrary/Documents/[^"]+\.pdf)"',
                row_html,
            )
            if not pdf_match:
                continue

            url = pdf_match.group(1)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            filename = url.rsplit("/", 1)[-1]

            # Extract all td values from this row
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            tds_clean = [_strip_html(td) for td in tds]

            # Map columns by index (from analysis):
            # Col 14 = Title, Col 15 = Topic, Col 17 = Year, Col 9 = Language
            title = tds_clean[14] if len(tds_clean) > 14 else ""
            topic = tds_clean[15] if len(tds_clean) > 15 else ""
            year_raw = tds_clean[17] if len(tds_clean) > 17 else ""
            language = tds_clean[9] if len(tds_clean) > 9 else ""

            year = _parse_year(year_raw)
            if not title:
                title = filename.replace(".pdf", "")

            docs.append({
                "url": url,
                "filename": filename,
                "title": title,
                "topic": topic,
                "year": year,
                "language": language,
            })

        return docs

    def _get_all_docs(self) -> List[Dict[str, str]]:
        """Fetch all documents across all paginated pages."""
        all_docs = []
        seen_urls = set()
        url = LIBRARY_URL

        for page_num in range(1, MAX_PAGES + 1):
            logger.info(f"Fetching library page {page_num}: {url}")
            html = self._get(url)
            if not html:
                logger.error(f"Failed to fetch page {page_num}")
                break

            page_docs = self._parse_library_page(html)
            new_count = 0
            for doc in page_docs:
                if doc["url"] not in seen_urls:
                    seen_urls.add(doc["url"])
                    all_docs.append(doc)
                    new_count += 1

            logger.info(f"Page {page_num}: found {new_count} new documents")

            if new_count == 0:
                break

            # Find next page link (forward only, highest PageFirstRow)
            next_matches = re.findall(
                r'Paged=TRUE[^"\']*?PageFirstRow=(\d+)[^"\']*',
                html,
            )
            if not next_matches:
                break

            # Pick the highest PageFirstRow that's beyond current position
            best_params = None
            best_row = 0
            for m in re.finditer(r'(Paged=TRUE[^"\']*?PageFirstRow=(\d+)[^"\']*)', html):
                row = int(m.group(2))
                if row > best_row:
                    best_row = row
                    best_params = m.group(1)

            if not best_params or best_row <= page_num * 30:
                break

            # Clean SharePoint URL artifacts
            best_params = best_params.replace("&amp;", "&")
            best_params = re.sub(r'["\'];.*$', "", best_params)
            best_params = re.sub(r'\);.*$', "", best_params)
            url = f"{LIBRARY_URL}?{best_params}"
            time.sleep(2)

        logger.info(f"Total documents found across all pages: {len(all_docs)}")
        return all_docs

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        docs = self._get_all_docs()
        limit = SAMPLE_LIMIT if sample else len(docs)
        count = 0

        for doc in docs:
            if count >= limit:
                break

            url = doc["url"]
            filename = doc["filename"]

            logger.info(f"Downloading: {filename}...")
            pdf_bytes = self._get_bytes(url)
            if not pdf_bytes:
                logger.warning(f"Failed to download: {url}")
                continue

            text = self._extract_pdf_text(pdf_bytes)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text ({len(text)} chars) for: {filename}")
                continue

            doc["text"] = text
            record = self.normalize(doc)

            count += 1
            logger.info(f"[{count}] {record['title'][:60]} ({len(text)} chars)")
            yield record
            time.sleep(2)

        logger.info(f"Finished: yielded {count} records from {len(docs)} documents")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(sample=False)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        title = raw.get("title", "")
        url = raw.get("url", "")
        filename = raw.get("filename", "")
        year = raw.get("year")
        topic = raw.get("topic", "")
        language = raw.get("language", "")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

        date = f"{year}-01-01" if year else None

        return {
            "_id": f"gcc-{url_hash}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": date,
            "url": url,
            "filename": filename,
            "topic": topic,
            "language": language,
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/GCC-LegalDocs bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = GCCLegalDocsScraper()

    if args.command == "test":
        html = scraper._get(LIBRARY_URL)
        if html and "DigitalLibrary" in html:
            docs = scraper._get_all_docs()
            print(f"OK: Connected to GCC digital library, found {len(docs)} PDF documents")
        else:
            print("FAIL: Could not fetch GCC digital library")
            sys.exit(1)
        return

    # Full corpus runs (bootstrap-fast, or bootstrap --full) stream to
    # data/records.jsonl so the whole set persists for VPS ingest.
    is_sample = args.sample or (args.command == "bootstrap" and not args.full)

    if not is_sample:
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        jsonl_path = data_dir / "records.jsonl"
        count = 0
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for record in scraper.fetch_all(sample=False):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                text_len = len(record.get("text", ""))
                print(f"  [{count}] {record['title'][:60]} ({text_len} chars)")
        print(f"\nDone: {count} records -> {jsonl_path}")
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)
    count = 0

    for record in scraper.fetch_all(sample=True):
        out_path = sample_dir / f"{count:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        count += 1
        text_len = len(record.get("text", ""))
        print(f"  [{count}] {record['title'][:60]} ({text_len} chars)")

    print(f"\nDone: {count} records saved to {sample_dir}/")


if __name__ == "__main__":
    main()
