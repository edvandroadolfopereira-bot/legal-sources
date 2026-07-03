#!/usr/bin/env python3
"""
INTL/ECOWAS-LegalDocs -- ECOWAS Treaties, Protocols, Conventions & Legal Instruments

Fetches legal instruments from ecowas.int publication categories:
  - Conventions (8 docs)
  - Protocols & Supplementary Protocols (49 docs)
  - Legal Texts on Regional Security (5 docs)
  - Digital Economy Legal Instruments (25 docs)
  - Session documents (decisions, supplementary acts)

Strategy:
  - Scrape HTML category pages for PDF download links
  - Download PDFs and extract text via pdfplumber
  - Normalize to standard schema

Usage:
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap --full     # Full fetch
  python bootstrap.py bootstrap-fast       # Alias for --full
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
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ECOWAS-LegalDocs")

SOURCE_ID = "INTL/ECOWAS-LegalDocs"
BASE_URL = "https://www.ecowas.int"

# Category pages containing legal instrument PDFs
CATEGORY_PAGES = [
    {
        "url": f"{BASE_URL}/publication/conventions/",
        "instrument_type": "convention",
    },
    {
        "url": f"{BASE_URL}/publication/supplementary-protocols/",
        "instrument_type": "protocol",
    },
    {
        "url": f"{BASE_URL}/publication/legal-texts-and-documents-on-regional-security-source-regional-security-division-rsd/",
        "instrument_type": "regulation",
    },
    {
        "url": f"{BASE_URL}/publication/directorate-of-digital-economy-and-post-technology-legal-instruments/",
        "instrument_type": "directive",
    },
    {
        "url": f"{BASE_URL}/publication/43rd-ordinary-session-of-the-authority-heads-of-state-and-government-abuja-17-18-july-2013/",
        "instrument_type": "decision",
    },
    {
        "url": f"{BASE_URL}/publication/45th-ordinary-session-of-the-authority-of-heads-of-state-and-government-accra-10-11-july-2014-3/",
        "instrument_type": "decision",
    },
    {
        "url": f"{BASE_URL}/publication/46th-ordinary-session-of-the-authority-of-heads-of-state-and-government-abuja-15-december-2014/",
        "instrument_type": "decision",
    },
]

# Skip non-legal files
SKIP_KEYWORDS = [
    "mp3", "choral", "anthem", ".jpg", ".png", "application form",
    "photo", "gallery", "video", "brochure", "flyer", "poster",
    "form.pdf",
]

# Max PDF size to download (15 MB)
MAX_PDF_SIZE = 15 * 1024 * 1024


class ECOWASLegalDocsScraper(BaseScraper):
    """
    Scraper for INTL/ECOWAS-LegalDocs.
    Country: INTL
    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _clean_title(self, title: str) -> str:
        """Clean title text."""
        # Remove file size suffixes like "0.15 MBpdf" or "5.03 MBpdf"
        title = re.sub(r"\d+\.\d+\s*MBpdf$", "", title).strip()
        title = re.sub(r"\d+\.\d+\s*MB\s*$", "", title).strip()
        title = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE).strip()
        title = title.replace("_", " ")
        title = re.sub(r"\s{2,}", " ", title)
        title = re.sub(r"\(\s*\d+\s*\)$", "", title).strip()
        return title

    def _extract_date(self, title: str, url: str) -> Optional[str]:
        """Try to extract a date from title or URL."""
        combined = f"{title} {url}"

        full_date = re.search(
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{4})", combined, re.IGNORECASE
        )
        if full_date:
            months = {
                "january": "01", "february": "02", "march": "03", "april": "04",
                "may": "05", "june": "06", "july": "07", "august": "08",
                "september": "09", "october": "10", "november": "11", "december": "12",
            }
            day = full_date.group(1).zfill(2)
            m = months.get(full_date.group(2).lower())
            yr = full_date.group(3)
            return f"{yr}-{m}-{day}"

        month_year = re.search(
            r"(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{4})", combined, re.IGNORECASE
        )
        if month_year:
            months = {
                "january": "01", "february": "02", "march": "03", "april": "04",
                "may": "05", "june": "06", "july": "07", "august": "08",
                "september": "09", "october": "10", "november": "11", "december": "12",
            }
            m = months.get(month_year.group(1).lower())
            yr = month_year.group(2)
            return f"{yr}-{m}-01"

        year_match = re.search(r",?\s*(19\d{2}|20\d{2})\b", title)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", combined)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        return None

    def _scrape_category_page(self, page_url: str, instrument_type: str) -> list[dict]:
        """Scrape a category page for PDF download links."""
        logger.info(f"Fetching {instrument_type} links from {page_url}")
        resp = self.session.get(page_url, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Only PDFs and DOCXs
            is_doc = href.lower().endswith(".pdf") or href.lower().endswith(".docx")
            if not is_doc:
                continue

            # Skip non-legal files
            href_lower = href.lower()
            if any(skip in href_lower for skip in SKIP_KEYWORDS):
                continue

            # Get title from link text or parent
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                parent = link.find_parent(["td", "p", "li", "div", "h3", "h4", "span"])
                if parent:
                    title = parent.get_text(strip=True)

            if not title or len(title) < 3:
                # Extract from filename
                filename = unquote(href.split("/")[-1])
                title = re.sub(r"\.(pdf|docx)$", "", filename, flags=re.IGNORECASE)
                title = title.replace("_", " ").replace("-", " ")

            title = self._clean_title(title)

            # Skip non-English duplicates (keep only EN versions when multi-language)
            title_lower = title.lower()
            # Only skip if there's a clear FR/PT suffix and it's a duplicate
            if href_lower.endswith("-fre.pdf") or href_lower.endswith("-por.pdf"):
                continue

            # Normalize URL
            if href.startswith("/"):
                href = BASE_URL + href
            elif not href.startswith("http"):
                href = BASE_URL + "/" + href

            # Only process PDFs (skip docx - no reliable extractor without python-docx)
            if not href.lower().endswith(".pdf"):
                continue

            date = self._extract_date(title, href)

            documents.append({
                "title": title,
                "url": href,
                "date": date,
                "instrument_type": instrument_type,
                "category_url": page_url,
            })

        logger.info(f"Found {len(documents)} {instrument_type} documents")
        return documents

    def _gather_all_documents(self) -> list[dict]:
        """Collect all document metadata from all category pages."""
        all_docs = []

        for cat in CATEGORY_PAGES:
            try:
                docs = self._scrape_category_page(cat["url"], cat["instrument_type"])
                all_docs.extend(docs)
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Failed to fetch {cat['instrument_type']} from {cat['url']}: {e}")

        # Deduplicate by normalized URL
        seen_urls = set()
        unique_docs = []
        for doc in all_docs:
            norm_url = doc["url"].replace("http://", "https://").rstrip("/").lower()
            # Normalize wp-content upload paths
            if "/wp-content/uploads/" in norm_url:
                # Extract just the filename for dedup
                norm_key = norm_url.split("/wp-content/uploads/")[-1]
            else:
                norm_key = norm_url
            if norm_key not in seen_urls:
                seen_urls.add(norm_key)
                unique_docs.append(doc)

        logger.info(f"Total unique documents: {len(unique_docs)}")
        return unique_docs

    def _download_pdf_text(self, url: str) -> str:
        """Download PDF and extract text via pdfplumber."""
        logger.info(f"Downloading PDF: {url[:100]}...")

        # HEAD request to check size
        try:
            head = self.session.head(url, timeout=30, allow_redirects=True)
            content_length = int(head.headers.get("Content-Length", 0))
            if content_length > MAX_PDF_SIZE:
                logger.warning(f"PDF too large ({content_length / 1024 / 1024:.1f} MB): {url[:80]}")
                return ""
        except Exception:
            pass

        resp = self.session.get(url, timeout=120)
        resp.raise_for_status()

        if len(resp.content) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({len(resp.content) / 1024 / 1024:.1f} MB): {url[:80]}")
            return ""

        if b"%PDF" not in resp.content[:1024]:
            logger.warning(f"Not a valid PDF: {url[:80]}")
            return ""

        text_parts = []
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            logger.info(f"  PDF has {len(pdf.pages)} pages")
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass

        full_text = "\n\n".join(text_parts)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        full_text = full_text.strip()

        logger.info(f"  Extracted {len(full_text)} chars from {len(text_parts)} pages")
        return full_text

    def _make_id(self, doc: dict) -> str:
        """Generate a stable unique ID from document URL."""
        key = doc["url"]
        return f"ecowas-ld-{hashlib.md5(key.encode()).hexdigest()[:12]}"

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legal instruments with full text."""
        documents = self._gather_all_documents()

        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Processing: {doc['title'][:70]}...")
            time.sleep(1.5)

            try:
                text = self._download_pdf_text(doc["url"])
            except Exception as e:
                logger.error(f"Failed to download {doc['url'][:80]}: {e}")
                continue

            if not text or len(text) < 200:
                logger.warning(f"Insufficient text ({len(text) if text else 0} chars) for: {doc['title'][:60]}")
                continue

            doc["text"] = text
            yield doc

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Re-fetch all (small corpus, no incremental updates)."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Normalize a raw document to standard schema."""
        text = raw.get("text", "")
        if not text:
            return None

        title = raw.get("title", "")
        url = raw.get("url", "")
        instrument_type = raw.get("instrument_type", "legislation")

        # Refine instrument_type from title
        title_lower = title.lower()
        if "treaty" in title_lower:
            instrument_type = "treaty"
        elif "convention" in title_lower:
            instrument_type = "convention"
        elif "protocol" in title_lower or "supplementary protocol" in title_lower:
            instrument_type = "protocol"
        elif "directive" in title_lower:
            instrument_type = "directive"
        elif "regulation" in title_lower:
            instrument_type = "regulation"
        elif "decision" in title_lower:
            instrument_type = "decision"
        elif "act" in title_lower:
            instrument_type = "act"

        return {
            "_id": self._make_id(raw),
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": url,
            "instrument_type": instrument_type,
            "organization": "ECOWAS",
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/ECOWAS-LegalDocs Data Fetcher")
    subparsers = parser.add_subparsers(dest="command")

    boot = subparsers.add_parser("bootstrap", help="Fetch data")
    boot.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast", help="Alias for bootstrap --full")
    subparsers.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()

    scraper = ECOWASLegalDocsScraper()

    if args.command == "bootstrap":
        if args.sample:
            stats = scraper.bootstrap(sample_mode=True, sample_size=15)
        elif args.full:
            stats = scraper.bootstrap(sample_mode=False)
        else:
            parser.print_help()
            return
        logger.info(f"Bootstrap stats: {json.dumps(stats, indent=2)}")
    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Bootstrap stats: {json.dumps(stats, indent=2)}")
    elif args.command == "test":
        logger.info("Testing connectivity...")
        docs = scraper._gather_all_documents()
        logger.info(f"Found {len(docs)} documents to fetch")
        for d in docs:
            logger.info(f"  - [{d['instrument_type']}] {d['title'][:70]}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
