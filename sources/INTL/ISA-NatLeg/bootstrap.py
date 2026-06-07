#!/usr/bin/env python3
"""
INTL/ISA-NatLeg -- ISA National Legislation Database

Fetches national legislation on deep seabed mining from the ISA website.

Strategy:
  - Fetch listing page at isa.org.jm/national-legislation-database/
  - Parse country headings and PDF links
  - Download PDFs and extract text via pdfplumber
  - Normalize into standard LDH schema

Data:
  - ~112 PDF documents from 50+ countries
  - Multiple languages (as submitted by member states)
  - No authentication required

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup4 required. pip install beautifulsoup4")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

try:
    from common.pdf_extract import extract_pdf_markdown
    HAS_PDF_EXTRACT = True
except ImportError:
    HAS_PDF_EXTRACT = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ISA-NatLeg")

BASE_URL = "https://isa.org.jm"
LISTING_URL = BASE_URL + "/national-legislation-database/"


class ISANatLegScraper(BaseScraper):
    """Scraper for INTL/ISA-NatLeg."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        })

    def _extract_pdf_text(self, content: bytes) -> Optional[str]:
        """Extract text from PDF content. Tries pdfplumber then PyMuPDF."""
        if HAS_PDF_EXTRACT:
            try:
                text = extract_pdf_markdown(content)
                if text and len(text.strip()) > 50:
                    return text.strip()
            except Exception:
                pass

        # Try pdfplumber first
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            text = "\n\n".join(pages).strip()
            if len(text) > 50:
                return text
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback to PyMuPDF
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            pages = [doc[i].get_text() for i in range(len(doc))]
            text = "\n\n".join(pages).strip()
            if len(text) > 50:
                return text
        except ImportError:
            logger.warning("No PDF extraction library available")
        except Exception as e:
            logger.warning("PDF extraction failed: %s", e)
        return None

    def _parse_listing(self, html: str) -> List[Dict[str, str]]:
        """Parse the listing page to extract country-grouped PDF entries."""
        soup = BeautifulSoup(html, "html.parser")
        entries = []
        seen_urls = set()
        current_country = "Unknown"

        content = soup.find("div", class_="entry-content") or soup.find("article") or soup
        # Country names are in <h5> tags; PDF links are in <a> tags
        for el in content.find_all(["h5", "a"]):
            if el.name == "h5":
                text = el.get_text(strip=True)
                if text and len(text) < 100:
                    current_country = text
            elif el.name == "a" and el.get("href", ""):
                href = el["href"]
                if ".pdf" not in href.lower():
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                title = el.get_text(strip=True)
                if not title:
                    title = href.split("/")[-1].replace(".pdf", "").replace("-", " ")
                pdf_url = href
                if not pdf_url.startswith("http"):
                    pdf_url = BASE_URL + pdf_url
                # Skip external PDFs (often 403/404)
                if "isa.org.jm" not in pdf_url:
                    continue
                entries.append({
                    "title": title,
                    "country": current_country,
                    "pdf_url": pdf_url,
                })

        return entries

    def _download_and_normalize(self, entry: Dict, idx: int) -> Optional[Dict[str, Any]]:
        """Download PDF and normalize."""
        title = entry["title"]
        pdf_url = entry["pdf_url"]

        self.rate_limiter.wait()
        try:
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to download %s: %s", title[:50], e)
            return None

        text = self._extract_pdf_text(resp.content)
        if not text:
            logger.warning("No text extracted from: %s", title[:50])
            return None

        url_hash = hashlib.md5(pdf_url.encode()).hexdigest()[:12]
        return {
            "_id": f"isa-natleg-{url_hash}",
            "_source": "INTL/ISA-NatLeg",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": None,
            "url": pdf_url,
            "country_origin": entry["country"],
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        self.rate_limiter.wait()
        resp = self.session.get(LISTING_URL, timeout=30)
        resp.raise_for_status()
        entries = self._parse_listing(resp.text)
        logger.info("Found %d PDF entries", len(entries))

        count = 0
        for i, entry in enumerate(entries):
            record = self._download_and_normalize(entry, i)
            if record:
                count += 1
                yield record
                if count % 20 == 0:
                    logger.info("Processed %d/%d", count, len(entries))
        logger.info("Total: %d records with text", count)

    def fetch_sample(self, n: int = 15) -> Generator[Dict[str, Any], None, None]:
        self.rate_limiter.wait()
        resp = self.session.get(LISTING_URL, timeout=30)
        resp.raise_for_status()
        entries = self._parse_listing(resp.text)

        count = 0
        for i, entry in enumerate(entries):
            if count >= n:
                return
            record = self._download_and_normalize(entry, i)
            if record:
                count += 1
                yield record

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/ISA-NatLeg scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = ISANatLegScraper()
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    if args.command == "test":
        logger.info("Testing connectivity...")
        try:
            resp = scraper.session.get(LISTING_URL, timeout=15)
            resp.raise_for_status()
            entries = scraper._parse_listing(resp.text)
            logger.info("Connected. Found %d PDF entries.", len(entries))
        except Exception as e:
            logger.error("Connection failed: %s", e)
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample or not args.full:
            logger.info("Fetching sample records...")
            count = 0
            for record in scraper.fetch_sample(15):
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                text_len = len(record.get("text", ""))
                logger.info("[%d] %s (%d chars)", count, record["title"][:60], text_len)
                count += 1
            logger.info("Saved %d sample records to %s", count, sample_dir)
        else:
            logger.info("Fetching all records...")
            count = 0
            for record in scraper.fetch_all():
                out = sample_dir / f"{count:04d}.json"
                out.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                count += 1
            logger.info("Saved %d records", count)
    elif args.command == "update":
        count = 0
        for record in scraper.fetch_all():
            count += 1
        logger.info("Fetched %d records", count)


if __name__ == "__main__":
    main()
