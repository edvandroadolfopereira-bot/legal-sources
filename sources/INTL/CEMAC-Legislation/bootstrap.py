#!/usr/bin/env python3
"""
INTL/CEMAC-Legislation -- CEMAC Legal Instruments

Fetches regulations, directives, treaties and conventions from cemac.int.

Strategy:
  - Scrapes listing pages for PDF download links
  - Downloads each PDF and extracts text with pdfplumber
  - Two sections: règlements-directives + traites-et-conventions

Data:
  - ~70 regulations, directives, treaties and conventions
  - Full text extracted from PDF documents
  - French language
  - Open access

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Same as bootstrap (small dataset)
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
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.CEMAC-Legislation")

BASE_URL = "https://cemac.int"
SECTIONS = [
    ("reglements-directives", "Règlements et Directives"),
    ("traities-conventiosns", "Traités et Conventions"),
]


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber, fallback to PyPDF2."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            text = "\n\n".join(pages)
    except Exception:
        pass

    if not text.strip():
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            text = "\n\n".join(pages)
        except Exception:
            pass

    return text.strip()


class CEMACLegislationScraper(BaseScraper):
    """
    Scraper for INTL/CEMAC-Legislation.
    Country: INTL
    URL: https://cemac.int/

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; contact@example.com)",
        })

    def _scrape_section(self, slug: str) -> list[dict]:
        """Scrape a section page for PDF document entries."""
        url = f"{BASE_URL}/{slug}/"
        logger.info(f"Fetching section: {url}")
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        entries = []
        seen_urls = set()

        # Find all links to PDFs in wp-content/uploads
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" not in href.lower():
                continue
            if "wp-content/uploads" not in href:
                continue

            full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Get title from link text or parent element
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                # Try parent td/div for title
                parent = a.find_parent("td") or a.find_parent("div") or a.find_parent("li")
                if parent:
                    title = parent.get_text(strip=True)

            # Try to extract date from nearby elements or URL path
            date_str = self._extract_date_from_context(a, full_url)

            entries.append({
                "title": title or "",
                "pdf_url": full_url,
                "date_str": date_str,
                "section": slug,
            })

        # Also check for entries that are table rows with title + download link
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            # Look for a PDF link in any td
            pdf_link = None
            for td in tds:
                a = td.find("a", href=True)
                if a and ".pdf" in a["href"].lower() and "wp-content/uploads" in a["href"]:
                    pdf_link = a
                    break
            if not pdf_link:
                continue

            full_url = pdf_link["href"] if pdf_link["href"].startswith("http") else urljoin(BASE_URL, pdf_link["href"])
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = tds[0].get_text(strip=True) if tds[0].get_text(strip=True) else ""
            date_str = self._extract_date_from_context(pdf_link, full_url)

            entries.append({
                "title": title,
                "pdf_url": full_url,
                "date_str": date_str,
                "section": slug,
            })

        logger.info(f"Found {len(entries)} documents in {slug}")
        return entries

    def _extract_date_from_context(self, element, url: str) -> str:
        """Try to extract a date from the surrounding HTML or the URL path."""
        # Check sibling/parent for date-like text
        parent = element.find_parent("tr") or element.find_parent("li") or element.find_parent("div")
        if parent:
            text = parent.get_text(separator=" ", strip=True)
            # Look for date patterns like "20 mai 2026", "6 mars 2025", etc.
            date_match = re.search(
                r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})',
                text, re.IGNORECASE
            )
            if date_match:
                return date_match.group(0)

            # Look for ISO-ish dates
            iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            if iso_match:
                return iso_match.group(1)

        # Fall back to extracting year/month from URL
        url_match = re.search(r'/uploads/(\d{4})/(\d{2})/', url)
        if url_match:
            return f"{url_match.group(1)}-{url_match.group(2)}"

        return ""

    def _parse_french_date(self, date_str: str) -> Optional[str]:
        """Parse French date strings to ISO 8601."""
        if not date_str:
            return None

        # Already ISO
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Year-month only from URL
        if re.match(r'^\d{4}-\d{2}$', date_str):
            return f"{date_str}-01"

        french_months = {
            'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
            'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
            'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
        }
        m = re.match(
            r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})',
            date_str, re.IGNORECASE
        )
        if m:
            day = int(m.group(1))
            month = french_months.get(m.group(2).lower(), 1)
            year = int(m.group(3))
            return f"{year:04d}-{month:02d}-{day:02d}"

        return None

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download a PDF file."""
        try:
            r = self.session.get(url, timeout=60)
            r.raise_for_status()
            if len(r.content) < 100:
                logger.warning(f"PDF too small ({len(r.content)} bytes): {url}")
                return None
            return r.content
        except Exception as e:
            logger.warning(f"Failed to download PDF {url}: {e}")
            return None

    def _make_doc_id(self, title: str, pdf_url: str) -> str:
        """Generate a stable document ID."""
        # Try to extract a regulation/directive number from the title
        num_match = re.search(r'[NnNn°°]\s*(\d[\d/\-]+)', title)
        if num_match:
            num = num_match.group(1).replace("/", "-")
            return f"CEMAC-{num}"

        # Fall back to URL-based hash
        slug = pdf_url.rstrip("/").split("/")[-1]
        slug = re.sub(r'\.pdf$', '', slug, flags=re.IGNORECASE)
        # Truncate long filenames
        if len(slug) > 80:
            slug = slug[:80]
        return f"CEMAC-{slug}"

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all CEMAC legal documents with full text."""
        all_entries = []
        for slug, label in SECTIONS:
            entries = self._scrape_section(slug)
            all_entries.extend(entries)
            time.sleep(1)

        logger.info(f"Total documents to process: {len(all_entries)}")

        for i, entry in enumerate(all_entries):
            logger.info(f"[{i+1}/{len(all_entries)}] Downloading: {entry['title'][:60]}...")

            pdf_bytes = self._download_pdf(entry["pdf_url"])
            if not pdf_bytes:
                continue

            text = _extract_pdf_text(pdf_bytes)
            if not text or len(text.strip()) < 50:
                logger.warning(f"Insufficient text from PDF: {entry['pdf_url']}")
                continue

            entry["text"] = text
            entry["pdf_size"] = len(pdf_bytes)
            yield entry
            time.sleep(1)

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Same as fetch_all for this small dataset."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw document data into standard schema."""
        text = raw.get("text", "")
        title = raw.get("title", "")
        pdf_url = raw.get("pdf_url", "")

        if not text or len(text.strip()) < 50:
            return None

        doc_id = self._make_doc_id(title, pdf_url)
        date = self._parse_french_date(raw.get("date_str", ""))

        # Determine document type from title
        doc_type = "regulation"
        title_lower = title.lower()
        if "directive" in title_lower:
            doc_type = "directive"
        elif "traité" in title_lower or "traite" in title_lower:
            doc_type = "treaty"
        elif "convention" in title_lower:
            doc_type = "convention"
        elif "additif" in title_lower:
            doc_type = "addendum"

        section = raw.get("section", "")
        section_label = ""
        for slug, label in SECTIONS:
            if slug == section:
                section_label = label
                break

        return {
            "_id": doc_id,
            "_source": "INTL/CEMAC-Legislation",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": pdf_url,
            "document_type": doc_type,
            "section": section_label,
            "organization": "CEMAC",
            "language": "fr",
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="INTL/CEMAC-Legislation data fetcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    bp = subparsers.add_parser("bootstrap", help="Full initial fetch")
    bp.add_argument("--sample", action="store_true", help="Fetch sample records only")
    bp.add_argument("--sample-size", type=int, default=15, help="Number of sample records")
    bp.add_argument("--full", action="store_true", help="Fetch all records")

    subparsers.add_parser("bootstrap-fast", help="Same as bootstrap (small dataset)")
    subparsers.add_parser("update", help="Incremental update")
    subparsers.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = CEMACLegislationScraper()

    if args.command == "test":
        logger.info("Testing connectivity...")
        try:
            entries = scraper._scrape_section("reglements-directives")
            logger.info(f"OK: Found {len(entries)} regulations/directives")
            if entries:
                logger.info(f"First: {entries[0]['title'][:60]}")
            entries2 = scraper._scrape_section("traites-et-conventions")
            logger.info(f"OK: Found {len(entries2)} treaties/conventions")
            logger.info("Connectivity test passed!")
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            sys.exit(1)

    elif args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = getattr(args, "sample", False)
        sample_size = getattr(args, "sample_size", 15)
        stats = scraper.bootstrap(
            sample_mode=sample_mode,
            sample_size=sample_size,
        )
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
