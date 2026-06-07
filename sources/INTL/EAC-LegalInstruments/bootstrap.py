#!/usr/bin/env python3
"""
INTL/EAC-LegalInstruments -- East African Community Treaty, Protocols, Acts & Regulations

Fetches legal instruments from:
  - eac.int/documents/category/protocols (protocols)
  - eac.int/documents/category/acts-of-the-community (acts, 2 pages)
  - eac.int/documents/category/eac-regulations (regulations)
  - eala.org/documents/category/acts-of-the-community (acts from EALA)
  - eacj.org/?page_id=33 (treaty full text, HTML)

Strategy:
  - Scrape HTML pages for PDF download links
  - Download PDFs and extract text via pdfplumber
  - Scrape Treaty HTML directly from EACJ
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
from urllib.parse import urljoin

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
logger = logging.getLogger("legal-data-hunter.INTL.EAC-LegalInstruments")

SOURCE_ID = "INTL/EAC-LegalInstruments"

# EAC document manager pages
EAC_BASE = "https://www.eac.int"
EAC_PROTOCOLS = f"{EAC_BASE}/documents/category/protocols"
EAC_ACTS_PAGE1 = f"{EAC_BASE}/documents/category/acts-of-the-community"
EAC_ACTS_PAGE2 = f"{EAC_BASE}/documents/category/acts-of-the-community?start=20"
EAC_REGULATIONS = f"{EAC_BASE}/documents/category/eac-regulations"

# EALA acts
EALA_ACTS = "https://www.eala.org/documents/category/acts-of-the-community"

# Treaty HTML from EACJ
EACJ_TREATY = "https://www.eacj.org/?page_id=33"


class EACLegalInstrumentsScraper(BaseScraper):
    """
    Scraper for INTL/EAC-LegalInstruments.
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
        """Clean title artifacts from web scraping."""
        title = re.sub(r"PDF$", "", title).strip()
        title = re.sub(r"PDF$", "", title).strip()  # double PDFPDF
        title = title.replace("_", " ")
        title = re.sub(r"\s{2,}", " ", title)
        title = re.sub(r"\(\s*\d+\s*\)$", "", title).strip()
        return title

    def _scrape_eac_documents(self, page_url: str, instrument_type: str) -> list[dict]:
        """Scrape eac.int document manager page for PDF download links."""
        logger.info(f"Fetching {instrument_type} links from {page_url}")
        resp = self.session.get(page_url, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        documents = []

        # EAC document manager uses links with controller=download
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Match download links or PDF links
            is_download = "controller=download" in href or href.endswith(".pdf")
            if not is_download:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                # Try parent element
                parent = link.find_parent(["td", "p", "li", "div", "h3", "h4"])
                if parent:
                    title = parent.get_text(strip=True)

            if not title or len(title) < 3:
                # Extract from filename parameter or URL
                if "name=" in href:
                    name_part = href.split("name=")[-1]
                    title = requests.utils.unquote(name_part).replace(".pdf", "").replace("_", " ").replace("-", " ")
                else:
                    title = href.split("/")[-1].replace(".pdf", "").replace("_", " ").replace("-", " ")

            # Clean title before further processing
            title = self._clean_title(title)

            # Skip non-legal downloads (images, audio, etc.)
            title_lower = title.lower()
            if any(skip in title_lower for skip in ["mp3", "choral", "anthem", ".jpg", ".png", "application form"]):
                continue

            # Normalize URL
            if href.startswith("/"):
                href = EAC_BASE + href
            elif not href.startswith("http"):
                href = EAC_BASE + "/" + href

            date = self._extract_date(title, href)

            documents.append({
                "title": title.strip(),
                "url": href,
                "date": date,
                "instrument_type": instrument_type,
                "source_site": "eac.int",
            })

        logger.info(f"Found {len(documents)} {instrument_type} documents from eac.int")
        return documents

    def _scrape_eala_acts(self) -> list[dict]:
        """Scrape EALA for Acts of the Community."""
        logger.info(f"Fetching acts from EALA: {EALA_ACTS}")
        resp = self.session.get(EALA_ACTS, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href.endswith(".pdf"):
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                parent = link.find_parent(["td", "p", "li", "div", "h3", "h4", "strong"])
                if parent:
                    title = parent.get_text(strip=True)
            if not title or len(title) < 5:
                title = href.split("/")[-1].replace(".pdf", "").replace("_", " ").replace("-", " ")

            # Normalize URL
            if href.startswith("/"):
                href = "https://www.eala.org" + href
            elif not href.startswith("http"):
                href = "https://www.eala.org/" + href

            date = self._extract_date(title, href)

            documents.append({
                "title": title.strip(),
                "url": href,
                "date": date,
                "instrument_type": "act",
                "source_site": "eala.org",
            })

        logger.info(f"Found {len(documents)} acts from EALA")
        return documents

    def _fetch_treaty_html(self) -> Optional[dict]:
        """Fetch the EAC Treaty full text from EACJ (HTML)."""
        logger.info(f"Fetching EAC Treaty from EACJ: {EACJ_TREATY}")
        resp = self.session.get(EACJ_TREATY, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find main content area
        content = soup.find("div", class_="entry-content") or soup.find("article") or soup.find("div", id="content")
        if not content:
            # Fallback: get all paragraph text
            paragraphs = soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "ol"])
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        else:
            # Clean the content
            for tag in content.find_all(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = content.get_text(separator="\n")

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) < 500:
            logger.warning(f"Treaty text too short ({len(text)} chars)")
            return None

        logger.info(f"Extracted treaty text: {len(text)} chars")
        return {
            "title": "Treaty for the Establishment of the East African Community (1999, as amended)",
            "url": EACJ_TREATY,
            "date": "1999-11-30",
            "instrument_type": "treaty",
            "source_site": "eacj.org",
            "text": text,
        }

    def _extract_date(self, title: str, url: str) -> Optional[str]:
        """Try to extract a date from document title or URL."""
        combined = f"{title} {url}"

        # Full date patterns: DD Month YYYY or Month DD, YYYY
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

        # Month Year pattern
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

        # Year from title (prefer years in title like "Act, 2019")
        year_match = re.search(r",?\s*(19\d{2}|20\d{2})\b", title)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        # Year from anywhere
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", combined)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        return None

    def _download_pdf_text(self, url: str) -> str:
        """Download PDF and extract text via pdfplumber."""
        logger.info(f"Downloading PDF: {url[:100]}...")
        resp = self.session.get(url, timeout=120)
        resp.raise_for_status()

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

        full_text = "\n\n".join(text_parts)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        full_text = full_text.strip()

        logger.info(f"  Extracted {len(full_text)} chars from {len(text_parts)} pages")
        return full_text

    def _make_id(self, doc: dict) -> str:
        """Generate a stable unique ID from document URL."""
        key = doc["url"]
        return f"eac-li-{hashlib.md5(key.encode()).hexdigest()[:12]}"

    def _gather_all_documents(self) -> list[dict]:
        """Collect all document metadata from all sources."""
        all_docs = []

        # 1. EAC Protocols
        try:
            protos = self._scrape_eac_documents(EAC_PROTOCOLS, "protocol")
            all_docs.extend(protos)
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Failed to fetch protocols: {e}")

        # 2. EAC Acts (page 1 and 2)
        for url in [EAC_ACTS_PAGE1, EAC_ACTS_PAGE2]:
            try:
                acts = self._scrape_eac_documents(url, "act")
                all_docs.extend(acts)
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Failed to fetch acts from {url}: {e}")

        # 3. EAC Regulations
        try:
            regs = self._scrape_eac_documents(EAC_REGULATIONS, "regulation")
            all_docs.extend(regs)
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Failed to fetch regulations: {e}")

        # 4. EALA Acts
        try:
            eala_acts = self._scrape_eala_acts()
            all_docs.extend(eala_acts)
        except Exception as e:
            logger.error(f"Failed to fetch EALA acts: {e}")

        # 5. Treaty from EACJ (HTML - already has text)
        try:
            treaty = self._fetch_treaty_html()
            if treaty:
                all_docs.append(treaty)
        except Exception as e:
            logger.error(f"Failed to fetch treaty: {e}")

        # Deduplicate by normalized URL
        seen_urls = set()
        unique_docs = []
        for doc in all_docs:
            norm_url = doc["url"].replace("http://", "https://").rstrip("/").lower()
            # Also normalize the file= parameter for eac.int downloads
            if "file=" in norm_url:
                file_id = re.search(r"file=([a-f0-9\-]+)", norm_url)
                if file_id:
                    norm_url = f"eac-file-{file_id.group(1)}"
            if norm_url not in seen_urls:
                seen_urls.add(norm_url)
                unique_docs.append(doc)

        logger.info(f"Total unique documents: {len(unique_docs)}")
        return unique_docs

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legal instruments with full text."""
        documents = self._gather_all_documents()

        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Processing: {doc['title'][:70]}...")
            time.sleep(1.5)

            # Treaty already has text from HTML
            if doc.get("text"):
                yield doc
                continue

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

        title = self._clean_title(raw.get("title", ""))
        url = raw.get("url", "")

        instrument_type = raw.get("instrument_type", "legislation")

        # Refine instrument_type from title
        title_lower = title.lower()
        if "treaty" in title_lower:
            instrument_type = "treaty"
        elif "protocol" in title_lower:
            instrument_type = "protocol"
        elif "regulation" in title_lower or "rules" in title_lower:
            instrument_type = "regulation"
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
            "organization": "EAC",
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/EAC-LegalInstruments Data Fetcher")
    subparsers = parser.add_subparsers(dest="command")

    boot = subparsers.add_parser("bootstrap", help="Fetch data")
    boot.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast", help="Alias for bootstrap --full")
    subparsers.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()

    scraper = EACLegalInstrumentsScraper()

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
            logger.info(f"  - [{d['instrument_type']}] {d['title'][:70]} ({d.get('source_site', '?')})")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
