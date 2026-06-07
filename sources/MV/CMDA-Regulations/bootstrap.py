#!/usr/bin/env python3
"""
MV/CMDA-Regulations -- Capital Market Development Authority of Maldives

Fetches CMDA's English-language capital-market regulatory corpus: regulations,
circulars, directives, and guidelines published at https://cmda.gov.mv/en/.

Documents are PDFs linked from individual regulation/download detail pages.
Full text is extracted with pdfplumber.

Sources scraped:
  - /en/regulations  (39 regulation detail pages)
  - /en/downloads?category=20  (circulars & directives, paginated, ~5 pages)
  - /en/guidelines  (guidelines & codes)

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # Sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Re-fetch (no incremental API)
  python bootstrap.py test               # Connectivity test
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
from urllib.parse import urljoin

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.MV.CMDA-Regulations")

BASE = "https://cmda.gov.mv"

DATE_RE = re.compile(
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4})"
)


class CMDAScraper(BaseScraper):
    """
    Scraper for MV/CMDA-Regulations.
    Country: MV
    URL: https://cmda.gov.mv/en

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

    @staticmethod
    def _parse_date(text: str) -> Optional[str]:
        """Extract and normalize a date string to ISO 8601."""
        m = DATE_RE.search(text)
        if not m:
            return None
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _get_regulation_slugs(self) -> list[str]:
        """Extract regulation detail page slugs from the listing page."""
        url = f"{BASE}/en/regulations"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch regulations listing: {e}")
            return []

        slugs = re.findall(
            r'https://cmda\.gov\.mv/en/regulations/([^"\'>\s]+)', resp.text
        )
        unique = sorted(set(slugs))
        logger.info(f"Found {len(unique)} regulation page slugs")
        return unique

    def _get_download_slugs(self, category: int, max_pages: int = 10) -> list[str]:
        """Extract download detail page slugs from a paginated category."""
        all_slugs = []
        seen = set()
        for page in range(1, max_pages + 1):
            url = f"{BASE}/en/downloads?category={category}&page={page}"
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                break

            slugs = re.findall(
                r'https://cmda\.gov\.mv/en/downloads/([^"\'>\s]+)', resp.text
            )
            new_slugs = [s for s in slugs if s not in seen and "?" not in s]
            if not new_slugs:
                break
            for s in new_slugs:
                seen.add(s)
                all_slugs.append(s)
            time.sleep(1.5)

        return all_slugs

    def _get_guideline_slugs(self) -> list[str]:
        """Extract guideline detail page slugs."""
        url = f"{BASE}/en/guidelines"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch guidelines listing: {e}")
            return []

        slugs = re.findall(
            r'https://cmda\.gov\.mv/en/downloads/([^"\'>\s]+)', resp.text
        )
        unique = sorted(set(s for s in slugs if "?" not in s))
        logger.info(f"Found {len(unique)} guideline slugs")
        return unique

    def _scrape_detail_page(self, page_url: str, category: str) -> Optional[dict]:
        """Scrape a detail page for PDF URL, title, and date."""
        try:
            resp = self.session.get(page_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch {page_url}: {e}")
            return None

        html = resp.text

        # Extract PDF URL from storage links
        pdf_urls = re.findall(
            r'(https://cmda\.gov\.mv/storage/uploads/[^"\'>\s]+\.pdf)', html
        )
        if not pdf_urls:
            logger.debug(f"No PDF found on {page_url}")
            return None
        pdf_url = pdf_urls[0]

        # Extract title from <title> tag
        title_match = re.search(r"<title>\s*(?:CMDA\s*-\s*)?(.+?)\s*</title>", html)
        title = title_match.group(1).strip() if title_match else ""

        # Extract date
        date = self._parse_date(html)

        return {
            "title": title,
            "date": date,
            "pdf_url": pdf_url,
            "page_url": page_url,
            "category": category,
        }

    def _collect_documents(self) -> list[dict]:
        """Collect all document metadata from regulations, circulars, and guidelines."""
        all_docs = []
        seen_pdfs = set()

        # 1. Regulations
        reg_slugs = self._get_regulation_slugs()
        for slug in reg_slugs:
            url = f"{BASE}/en/regulations/{slug}"
            doc = self._scrape_detail_page(url, "regulation")
            if doc and doc["pdf_url"] not in seen_pdfs:
                seen_pdfs.add(doc["pdf_url"])
                all_docs.append(doc)
            time.sleep(1.5)

        logger.info(f"After regulations: {len(all_docs)} docs")

        # 2. Circulars & Directives (category=20)
        circ_slugs = self._get_download_slugs(20, max_pages=6)
        for slug in circ_slugs:
            url = f"{BASE}/en/downloads/{slug}"
            doc = self._scrape_detail_page(url, "circular")
            if doc and doc["pdf_url"] not in seen_pdfs:
                seen_pdfs.add(doc["pdf_url"])
                all_docs.append(doc)
            time.sleep(1.5)

        logger.info(f"After circulars: {len(all_docs)} docs")

        # 3. Guidelines
        guide_slugs = self._get_guideline_slugs()
        for slug in guide_slugs:
            url = f"{BASE}/en/downloads/{slug}"
            doc = self._scrape_detail_page(url, "guideline")
            if doc and doc["pdf_url"] not in seen_pdfs:
                seen_pdfs.add(doc["pdf_url"])
                all_docs.append(doc)
            time.sleep(1.5)

        logger.info(f"Total collected: {len(all_docs)} docs")
        return all_docs

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract its text via pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=120)
        except Exception as e:
            logger.warning(f"Failed to download {pdf_url}: {e}")
            return None

        ctype = resp.headers.get("content-type", "")
        if resp.status_code != 200 or len(resp.content) < 500:
            logger.warning(f"Bad response ({resp.status_code}): {pdf_url}")
            return None

        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages = [p.extract_text() or "" for p in pdf.pages]
            pdf.close()
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return None

        text = "\n\n".join(p for p in pages if p.strip())
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text if len(text) >= 200 else None

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform a raw document into the standard schema."""
        text = (raw.get("text") or "").strip()
        if len(text) < 200:
            return None
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        url_hash = hashlib.md5(raw["pdf_url"].encode("utf-8")).hexdigest()[:12]
        doc_id = f"MV-CMDA-{url_hash}"

        return {
            "_id": doc_id,
            "_source": "MV/CMDA-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": raw.get("page_url", raw["pdf_url"]),
            "category": raw.get("category", ""),
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Fetch all CMDA regulatory documents with full PDF text."""
        documents = self._collect_documents()
        logger.info(f"Processing {len(documents)} documents")

        yielded = 0
        skipped = 0
        for doc in documents:
            text = self._extract_pdf_text(doc["pdf_url"])
            if not text:
                skipped += 1
                continue
            doc["text"] = text
            normalized = self.normalize(doc)
            if normalized:
                yielded += 1
                yield normalized
            else:
                skipped += 1
            time.sleep(2)

        logger.info(f"Done. Yielded: {yielded}, Skipped: {skipped}")

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """No incremental API; re-fetch everything."""
        yield from self.fetch_all()

    def test(self) -> dict:
        """Quick connectivity test."""
        url = f"{BASE}/en/regulations"
        resp = self.session.get(url, timeout=30)
        return {
            "status": "ok" if resp.status_code == 200 else "error",
            "http_code": resp.status_code,
            "url": url,
        }


if __name__ == "__main__":
    scraper = CMDAScraper()

    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test":
        print(json.dumps(scraper.test(), indent=2))
    elif command in ("bootstrap", "bootstrap-fast", "update"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        gen = scraper.fetch_all() if command != "update" else scraper.fetch_updates()
        count = 0
        limit = 20 if sample_mode else 99999
        for record in gen:
            count += 1
            if sample_mode:
                outpath = sample_dir / f"{count:04d}.json"
                outpath.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                print(f"[{count}] {record['title'][:60]} ({len(record['text'])} chars)")
            else:
                print(json.dumps(record, ensure_ascii=False))
            if count >= limit:
                break
        print(f"\nTotal records: {count}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
