#!/usr/bin/env python3
"""
TD/FinancesCodesLois -- Chad Ministry of Finance Tax Codes & Finance Laws

Scrapes the Joomla-based publications page at finances.gouv.td for
tax codes, customs codes, and finance laws. Downloads PDFs and extracts text.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Incremental update
"""

import sys
import json
import logging
import re
import io
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator
from html import unescape

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.TD.FinancesCodesLois")

SOURCE_ID = "TD/FinancesCodesLois"
BASE_URL = "https://finances.gouv.td"
LIST_URL = f"{BASE_URL}/index.php/publications/codes-lois-textes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}

SAMPLE_LIMIT = 15
PAGE_SIZE = 20


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return _clean_text("\n\n".join(pages_text))
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return ""


def _parse_document_list(html: str) -> list:
    """Extract documents from the Joomla table HTML."""
    docs = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 3:
            continue

        # Title from first cell
        title_m = re.search(r"<a[^>]*>(.*?)</a>", cells[0], re.DOTALL)
        title = unescape(re.sub(r"<[^>]+>", "", title_m.group(1) if title_m else cells[0])).strip()

        # Download ID
        dl_m = re.search(r"id=(\d+)", row)
        if not dl_m or not title:
            continue

        doc_id = dl_m.group(1)

        # Try to get file size from last cell
        size_text = re.sub(r"<[^>]+>", "", cells[-1]).strip() if cells else ""

        docs.append({
            "download_id": doc_id,
            "title": title,
            "size_text": size_text,
        })

    return docs


class SourceScraper(BaseScraper):
    """
    Scraper for: Chad Ministry of Finance Tax Codes & Finance Laws
    Country: TD
    URL: https://finances.gouv.td/index.php/publications/codes-lois-textes

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url="",
            headers=HEADERS,
        )

    def _get_all_documents(self) -> list:
        """Fetch all document metadata from paginated list."""
        all_docs = []
        start = 0

        while True:
            url = f"{LIST_URL}?start={start}" if start > 0 else LIST_URL
            logger.info(f"Fetching list page (start={start})...")
            resp = self.client.get(url)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                break

            docs = _parse_document_list(resp.text)
            if not docs:
                break

            all_docs.extend(docs)
            logger.info(f"Found {len(docs)} documents on this page (total: {len(all_docs)})")

            # Check for next page
            if f"start={start + PAGE_SIZE}" in resp.text:
                start += PAGE_SIZE
                time.sleep(1.5)
            else:
                break

        # Deduplicate by download_id
        seen = set()
        unique = []
        for d in all_docs:
            if d["download_id"] not in seen:
                seen.add(d["download_id"])
                unique.append(d)

        logger.info(f"Total unique documents: {len(unique)}")
        return unique

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all documents with full text from PDF."""
        documents = self._get_all_documents()

        for i, doc in enumerate(documents):
            download_url = f"{LIST_URL}?view=download&id={doc['download_id']}"
            title = doc["title"]

            logger.info(f"[{i+1}/{len(documents)}] Downloading: {title[:60]}...")
            time.sleep(1.5)

            try:
                resp = self.client.get(download_url)
                if resp.status_code != 200:
                    logger.warning(f"HTTP {resp.status_code} for ID {doc['download_id']}")
                    continue
                pdf_bytes = resp.content
            except Exception as e:
                logger.warning(f"Download failed: {e}")
                continue

            # Verify it's a PDF
            if not pdf_bytes[:4] == b"%PDF":
                logger.warning(f"Not a PDF for ID {doc['download_id']} (got {pdf_bytes[:20]})")
                continue

            text = _extract_pdf_text(pdf_bytes)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text from {title}: {len(text)} chars")
                continue

            # Extract date from title if possible (e.g., "2017_LOI N°429...")
            date = None
            year_m = re.search(r"(20\d{2})", title)
            if year_m:
                date = f"{year_m.group(1)}-01-01"

            # Get filename from Content-Disposition
            cd = resp.headers.get("content-disposition", "")
            filename_m = re.search(r'filename="([^"]+)"', cd)
            filename = filename_m.group(1) if filename_m else f"doc_{doc['download_id']}.pdf"

            doc_hash = hashlib.sha256(download_url.encode()).hexdigest()[:12]

            yield {
                "_id": f"td-finance-{doc['download_id']}-{doc_hash}",
                "_source": SOURCE_ID,
                "_type": "legislation",
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "text": text,
                "date": date,
                "url": download_url,
                "filename": filename,
                "pdf_size_bytes": len(pdf_bytes),
            }

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Small corpus — re-fetch all on update."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        return raw


def main():
    scraper = SourceScraper()
    args = sys.argv[1:]

    if not args:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update] [--sample]")
        sys.exit(1)

    command = args[0]
    sample = "--sample" in args or "--samples" in args

    if command in ("bootstrap", "bootstrap-fast"):
        records = []
        for rec in scraper.fetch_all():
            records.append(rec)
            if sample and len(records) >= SAMPLE_LIMIT:
                break

        if sample:
            sample_dir = Path(__file__).parent / "sample"
            sample_dir.mkdir(exist_ok=True)
            for rec in records:
                fname = re.sub(r"[^a-zA-Z0-9_-]", "_", rec["_id"]) + ".json"
                with open(sample_dir / fname, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(records)} sample records to {sample_dir}")
        else:
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logger.info(f"Wrote {len(records)} records to {jsonl_path}")

        logger.info(f"Total: {len(records)} records")
        for rec in records[:3]:
            logger.info(f"  {rec['title'][:60]} | text={len(rec.get('text',''))} chars")

    elif command == "update":
        logger.info("Small corpus — running full fetch")
        count = 0
        for rec in scraper.fetch_all():
            count += 1
        logger.info(f"Updated {count} records")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
