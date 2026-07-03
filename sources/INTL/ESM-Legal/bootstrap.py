#!/usr/bin/env python3
"""
INTL/ESM-Legal -- European Stability Mechanism Governance Documents

Fetches governance documents from the ESM transparency pages:
  1. ESM Policies & Legal Documents (Treaty, By-Laws, guidelines, etc.)
  2. Programme BoG/BoD Decisions (meeting summaries, agendas)
  3. Board of Auditors Key Documents (annual reports, management comments)

Strategy:
  - Parse three transparency section pages for PDF links
  - Download each PDF from esm.europa.eu/system/files
  - Extract full text using pdfplumber
  - ~105 documents total

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
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
from urllib.parse import urljoin, unquote

import requests
import pdfplumber
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ESM-Legal")

BASE_URL = "https://www.esm.europa.eu"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

SECTIONS = [
    {
        "path": "/about-us/transparency/esm-policies-documents",
        "label": "ESM Policies & Legal Documents",
        "parser": "policies",
    },
    {
        "path": "/about-us/transparency/programme-bog-bod-decisions",
        "label": "Programme BoG/BoD Decisions",
        "parser": "decisions",
    },
    {
        "path": "/about-us/transparency/boa-key-documents",
        "label": "Board of Auditors Key Documents",
        "parser": "decisions",
    },
]


def extract_date(title: str, pdf_url: str) -> Optional[str]:
    """Extract a date from the title or PDF URL/filename."""
    # Try patterns like "19 June 2025", "25 June 2024"
    m = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+(\d{4})",
        title, re.IGNORECASE,
    )
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Try ISO-style dates in URL: 2024-06-25 or 2024-06-17
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", unquote(pdf_url))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Try YYYYMMDD in URL
    m = re.search(r"(\d{4})(\d{2})(\d{2})", unquote(pdf_url))
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # Try year-month in URL path like /document/2025-06/
    m = re.search(r"/document/(\d{4})-(\d{2})/", pdf_url)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # Try just a year from the title
    m = re.search(r"\b(20\d{2})\b", title)
    if m:
        return m.group(1)

    # Try year from URL
    m = re.search(r"(\d{4})_", unquote(pdf_url))
    if m and 2000 <= int(m.group(1)) <= 2030:
        return m.group(1)

    return None


def make_doc_id(title: str, pdf_url: str) -> str:
    """Create a stable document ID from the title and PDF URL."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:80]
    url_hash = hashlib.md5(pdf_url.encode()).hexdigest()[:8]
    return f"esm-{slug}-{url_hash}"


def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(pages)
    except Exception as e:
        logger.warning("pdfplumber failed: %s", e)
        return ""


def parse_policies_page(soup: BeautifulSoup) -> list:
    """Parse the ESM Policies & Legal Documents page.

    Structure: <li> items inside item-list, each with:
      - div.views-field-field-esm-term (category)
      - div.views-field-title > a[href=*.pdf] (title + link)
    """
    docs = []
    view = soup.find("div", class_="transparency-documents")
    if not view:
        view = soup

    for li in view.find_all("li"):
        a = li.find("a", href=lambda h: h and ".pdf" in h)
        if not a:
            continue
        title = a.get_text(strip=True)
        pdf_href = a["href"]

        cat_div = li.find("div", class_="views-field-field-esm-term")
        category = cat_div.get_text(strip=True) if cat_div else ""

        docs.append({"title": title, "pdf_href": pdf_href, "category": category})
    return docs


def parse_decisions_page(soup: BeautifulSoup) -> list:
    """Parse BoG/BoD Decisions or BoA Key Documents page.

    Structure: div.views-row items, each with a single PDF link.
    """
    docs = []
    for row in soup.find_all("div", class_="views-row"):
        a = row.find("a", href=lambda h: h and ".pdf" in h)
        if not a:
            continue
        title = a.get_text(strip=True)
        pdf_href = a["href"]
        docs.append({"title": title, "pdf_href": pdf_href, "category": ""})
    return docs


class ESMLegalScraper(BaseScraper):
    SOURCE_ID = "INTL/ESM-Legal"

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch_section(self, section: dict) -> list:
        """Fetch and parse a single transparency section page."""
        url = BASE_URL + section["path"]
        logger.info("Fetching section: %s", section["label"])

        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        if section["parser"] == "policies":
            docs = parse_policies_page(soup)
        else:
            docs = parse_decisions_page(soup)

        for doc in docs:
            doc["section"] = section["label"]
            if not doc["pdf_href"].startswith("http"):
                doc["pdf_href"] = BASE_URL + doc["pdf_href"]

        logger.info("  Found %d documents in %s", len(docs), section["label"])
        return docs

    def _download_pdf_text(self, pdf_url: str) -> str:
        """Download a PDF and extract its text."""
        resp = self.session.get(pdf_url, timeout=60)
        resp.raise_for_status()
        return extract_text_from_pdf(resp.content)

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield raw document metadata (title + PDF link) for every section.

        Per the BaseScraper contract, fetch_all yields RAW records; the
        framework calls normalize(raw) (concurrently, in bootstrap_fast),
        which downloads the PDF and extracts full text.
        """
        all_docs = []
        for section in SECTIONS:
            try:
                docs = self._fetch_section(section)
                all_docs.extend(docs)
                time.sleep(1)
            except Exception as e:
                logger.error("Failed to fetch section %s: %s", section["label"], e)

        logger.info("Total documents found: %d", len(all_docs))
        for doc in all_docs:
            yield doc

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Fetch all docs (small corpus, no incremental endpoint)."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> Optional[dict]:
        """Download the PDF, extract full text, return the standard schema.

        Returns None (intentional skip) if the PDF is unreachable or yields
        insufficient text.
        """
        title = raw["title"]
        pdf_url = raw["pdf_href"]

        try:
            text = self._download_pdf_text(pdf_url)
        except Exception as e:
            logger.warning("  Failed to download %s: %s", title[:50], e)
            return None

        if not text or len(text.strip()) < 50:
            logger.warning("  Insufficient text (%d chars) for %s",
                           len(text or ""), title[:50])
            return None

        doc_id = make_doc_id(title, pdf_url)
        date = extract_date(title, pdf_url)

        return {
            "_id": doc_id,
            "_source": "INTL/ESM-Legal",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text.strip(),
            "date": date,
            "url": pdf_url,
            "category": raw.get("category", ""),
            "section": raw.get("section", ""),
        }

    # ── CLI entry point ──────────────────────────────────────────────

    def test_connection(self) -> bool:
        """Quick connectivity check."""
        try:
            resp = self.session.get(
                BASE_URL + SECTIONS[0]["path"], timeout=15
            )
            ok = resp.status_code == 200 and ".pdf" in resp.text
            logger.info("Connection test: %s (status %d)", "OK" if ok else "FAIL", resp.status_code)
            return ok
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/ESM-Legal data fetcher")
    parser.add_argument(
        "command", choices=["bootstrap", "bootstrap-fast", "update", "test"]
    )
    parser.add_argument("--sample", action="store_true", help="Fetch 15 samples only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = ESMLegalScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test_connection() else 1)

    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap_fast()
        logger.info("Done: %s", stats)

    elif args.command in ("bootstrap", "update"):
        stats = scraper.bootstrap(sample_mode=args.sample, sample_size=15)
        logger.info("Done: %s", stats)


if __name__ == "__main__":
    main()
