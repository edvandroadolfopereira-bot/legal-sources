#!/usr/bin/env python3
"""
INTL/UPU-Acts -- Universal Postal Union Acts and Convention Texts

Fetches official UPU legal instruments from the Acts page:
  - Constitution (1964) + 11 Additional Protocols (Tokyo 1969 – Abidjan 2021)
  - General Regulations + Additional Protocols
  - Universal Postal Convention + Postal Payment Services Agreement
  - Congress Acts (1999–2025)
  - Convention Manuals and Regulations

Strategy:
  - Parse the Acts HTML page for PDF links (<a href="/UPU/media/...pdf">)
  - Download each PDF and extract full text with pdfplumber
  - ~70 documents total

Endpoints:
  - Acts page: https://www.upu.int/en/universal-postal-union/about-upu/acts
  - PDFs:      https://www.upu.int/UPU/media/upu/files/aboutUpu/acts/...

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
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from html import unescape

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.UPU-Acts")

BASE_URL = "https://www.upu.int"
ACTS_URL = f"{BASE_URL}/en/universal-postal-union/about-upu/acts"
SOURCE_ID = "INTL/UPU-Acts"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (research; +https://legaldatahunter.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SAMPLE_LIMIT = 15


def _clean_text(text: str) -> str:
    """Tidy extracted PDF text."""
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _make_id(title: str, url: str) -> str:
    """Generate a stable document ID from title and URL."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"upu-{slug}-{url_hash}"


def _extract_year(title: str, url: str) -> Optional[str]:
    """Try to extract a year from the document title or URL."""
    for text in [title, url]:
        m = re.search(r"(19\d{2}|20\d{2})", text)
        if m:
            return m.group(1)
    return None


class UPUActsScraper(BaseScraper):
    SOURCE_ID = SOURCE_ID

    def __init__(self):
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
        """Extract text from PDF bytes using pdfplumber."""
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
            return _clean_text("\n\n".join(pages))
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return ""

    def _parse_acts_page(self) -> List[Dict[str, str]]:
        """Parse the UPU acts page and extract PDF links with titles."""
        html = self._get(ACTS_URL)
        if not html:
            logger.error("Failed to fetch acts page")
            return []

        # Find all PDF links: <a href="/UPU/media/...pdf">Title text</a>
        pattern = re.compile(
            r'<a[^>]+href="(/UPU/media/upu/files/[^"]+\.pdf)"[^>]*>(.*?)</a>',
            re.S,
        )

        docs = []
        seen_urls = set()

        for match in pattern.finditer(html):
            path = match.group(1)
            title_raw = match.group(2)

            # Clean title: strip HTML tags and decode entities
            title = re.sub(r"<[^>]+>", "", title_raw)
            title = unescape(title).strip()

            if not title or path in seen_urls:
                continue

            seen_urls.add(path)
            full_url = f"{BASE_URL}{path}"

            docs.append({
                "title": title,
                "url": full_url,
                "path": path,
            })

        logger.info(f"Found {len(docs)} PDF documents on acts page")
        return docs

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Fetch all UPU acts and extract full text."""
        docs = self._parse_acts_page()
        limit = SAMPLE_LIMIT if sample else len(docs)
        count = 0

        for doc in docs:
            if count >= limit:
                break

            title = doc["title"]
            url = doc["url"]

            logger.info(f"Downloading: {title[:60]}...")
            pdf_bytes = self._get_bytes(url)
            if not pdf_bytes:
                logger.warning(f"Failed to download PDF: {url}")
                continue

            text = self._extract_pdf_text(pdf_bytes)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text ({len(text)} chars) for: {title[:60]}")
                continue

            year = _extract_year(title, url)
            date = f"{year}-01-01" if year else None

            record = self.normalize({
                "title": title,
                "text": text,
                "url": url,
                "date": date,
                "year": year,
            })

            count += 1
            logger.info(f"[{count}] {title[:60]} ({len(text)} chars)")
            yield record
            time.sleep(2)

        logger.info(f"Finished: yielded {count} records from {len(docs)} documents")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(sample=False)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        title = raw.get("title", "")
        url = raw.get("url", "")

        return {
            "_id": _make_id(title, url),
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "url": url,
            "year": raw.get("year"),
        }


# --------------- CLI ---------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/UPU-Acts bootstrap")
    parser.add_argument("command", choices=["bootstrap", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = UPUActsScraper()

    if args.command == "test":
        html = scraper._get(ACTS_URL)
        if html and "Universal Postal" in html:
            docs = scraper._parse_acts_page()
            print(f"OK: Connected to UPU acts page, found {len(docs)} PDF documents")
        else:
            print("FAIL: Could not fetch UPU acts page")
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
