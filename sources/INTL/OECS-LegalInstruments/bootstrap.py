#!/usr/bin/env python3
"""
INTL/OECS-LegalInstruments -- OECS Authority Communiqués & Legal Instruments

Fetches legal instruments from the Organisation of Eastern Caribbean States:
  - Authority communiqués (meetings 64th–77th+, special & emergency meetings)
  - ECCB Monetary Council communiqués
  - OECS Authority statements and declarations
  - Revised Treaty of Basseterre (PDF, if pdfplumber available)
  - Legal service documents (PDFs, if pdfplumber available)

Strategy:
  - Parse pressroom.oecs.int sitemap.xml for communiqué/statement URLs
  - Fetch each via Prezly JSON endpoint (.json suffix) for structured full text
  - Optionally download legal library PDFs (Treaty etc.) via pdfplumber

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
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.OECS-LegalInstruments")

SOURCE_ID = "INTL/OECS-LegalInstruments"
PRESSROOM_BASE = "https://pressroom.oecs.int"
OECS_BASE = "https://oecs.int"

# Keywords to identify legal/authority content in sitemap URLs
LEGAL_SLUG_PATTERNS = [
    "communique-of-the-",
    "communique-special-meeting",
    "communique-continuation",
    "communique-88th-meeting-of-monetary",
    "communique-of-the-1st-special-meeting-of-the-monetary",
    "communique-of-the-95th-meeting-of-the-monetary",
    "communique-of-the-92nd-meeting-of-the-monetary",
    "communique-of-the-93rd-meeting-of-the-monetary",
    "communique-of-the-108th-meeting-of-the-monetary",
    "communique-of-the-7th-meeting-of-the-oecs-council",
    "communique-of-the-emergency-meeting",
    "statement-by-the-protocol-member-states",
    "statement-by-the-oecs-authority",
    "76th-oecs-authority-meeting",
    "ecsc-statement-on-justice",
    "draft-legislation-for-the-establishment-of-cbicip",
    "caribbean-leaders-unite-for-collective-action-on-oceans",
]

# Additional legal library PDFs (downloaded if pdfplumber available)
LEGAL_LIBRARY_DOCS = [
    {
        "title": "Revised Treaty of Basseterre Establishing the OECS Economic Union",
        "url": f"{OECS_BASE}/en/our-work/knowledge/library/revised-treaty-of-basseterre/download",
        "instrument_type": "treaty",
        "date": "2010-06-18",
    },
    {
        "title": "OECS Family Law and Domestic Violence Reform Initiative (Green Paper)",
        "url": f"{OECS_BASE}/en/our-work/knowledge/library/oecs-family-law-and-domestic-violence-reform-initiative-green-paper/download",
        "instrument_type": "reform_paper",
        "date": "2016-09-14",
    },
    {
        "title": "Protecting Eastern Caribbean Economies from Criminal Proceeds — Recommendations",
        "url": f"{OECS_BASE}/en/our-work/knowledge/library/protecting-eastern-caribbean-economies-from-the-dangers-of-criminal-proceeds-reccomendations-proceedings-pdf/download",
        "instrument_type": "regulation",
        "date": "2000-06-30",
    },
    {
        "title": "Free Movement of OECS Citizens — Administrative Arrangements and Procedures",
        "url": f"{OECS_BASE}/en/our-work/knowledge/library/free-movement-of-oecs-citizens-administrative-arrangements-and-procedures/download",
        "instrument_type": "regulation",
        "date": "2011-08-01",
    },
]

MAX_PDF_SIZE = 15 * 1024 * 1024


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities, preserving paragraph breaks."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<blockquote[^>]*>", "\n> ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


class OECSLegalInstrumentsScraper(BaseScraper):
    """Scraper for INTL/OECS-LegalInstruments."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "application/json, text/html, application/xml",
        })

    def _fetch_sitemap_urls(self) -> list[str]:
        """Fetch and parse pressroom sitemap for legal content URLs."""
        sitemap_url = f"{PRESSROOM_BASE}/sitemap.xml"
        logger.info(f"Fetching sitemap: {sitemap_url}")
        resp = self.session.get(sitemap_url, timeout=60)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        urls = []
        for url_elem in root.findall("sm:url", ns):
            loc = url_elem.find("sm:loc", ns)
            if loc is None or loc.text is None:
                continue
            url = loc.text.strip()
            # Skip French/Spanish translations and category pages
            if "/fr/" in url or "/es/" in url or "/fr" == url[-3:] or "/es" == url[-3:]:
                continue
            if "/category/" in url:
                continue
            urls.append(url)

        return urls

    def _filter_legal_urls(self, urls: list[str]) -> list[str]:
        """Filter sitemap URLs for legal/authority content."""
        legal_urls = []
        for url in urls:
            slug = url.split("/")[-1].lower()
            if any(pattern in slug for pattern in LEGAL_SLUG_PATTERNS):
                legal_urls.append(url)
            elif "communiqu" in slug and ("authority" in slug or "monetary" in slug or "oecs" in slug):
                legal_urls.append(url)

        logger.info(f"Found {len(legal_urls)} legal/authority URLs in sitemap")
        return legal_urls

    def _fetch_prezly_json(self, url: str) -> Optional[dict]:
        """Fetch a story via Prezly JSON endpoint (append .json to URL)."""
        json_url = url.rstrip("/") + ".json"
        logger.info(f"Fetching JSON: {json_url[:80]}...")

        try:
            resp = self.session.get(json_url, timeout=60)
            if resp.status_code == 404:
                logger.warning(f"JSON endpoint not found for {url[:60]}")
                return None
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch JSON for {url[:60]}: {e}")
            return None

    def _fetch_pdf_text(self, url: str) -> str:
        """Download PDF and extract text via pdfplumber."""
        if not HAS_PDFPLUMBER:
            logger.warning("pdfplumber not available, skipping PDF")
            return ""

        logger.info(f"Downloading PDF: {url[:80]}...")
        resp = self.session.get(url, timeout=120, allow_redirects=True)
        resp.raise_for_status()

        if len(resp.content) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({len(resp.content) / 1024 / 1024:.1f} MB)")
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
        return full_text.strip()

    def _make_id(self, url: str) -> str:
        """Generate a stable unique ID from URL."""
        norm = url.replace("pressroom.oecs.org", "pressroom.oecs.int").rstrip("/").lower()
        return f"oecs-li-{hashlib.md5(norm.encode()).hexdigest()[:12]}"

    def _classify_instrument(self, title: str, tags: list[str]) -> str:
        """Determine instrument type from title and tags."""
        title_lower = title.lower()
        if "treaty" in title_lower:
            return "treaty"
        if "protocol" in title_lower:
            return "protocol"
        if "declaration" in title_lower:
            return "declaration"
        if "statement" in title_lower:
            return "statement"
        if "legislation" in title_lower or "draft" in title_lower:
            return "model_legislation"
        if "monetary council" in title_lower or "eccb" in title_lower:
            return "monetary_council_communiqué"
        return "communiqué"

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legal instruments with full text."""
        # 1. Pressroom communiqués via Prezly JSON API
        sitemap_urls = self._fetch_sitemap_urls()
        legal_urls = self._filter_legal_urls(sitemap_urls)

        count = 0
        for i, url in enumerate(legal_urls):
            logger.info(f"[{i+1}/{len(legal_urls)}] Processing: {url.split('/')[-1][:60]}...")
            time.sleep(1.5)

            story = self._fetch_prezly_json(url)
            if not story:
                continue

            body_html = story.get("body", "")
            intro_html = story.get("intro", "")
            full_html = intro_html + "\n" + body_html if intro_html else body_html
            text = strip_html(full_html)

            if not text or len(text) < 100:
                logger.warning(f"Insufficient text ({len(text) if text else 0} chars): {url.split('/')[-1][:50]}")
                continue

            title = story.get("title", "")
            tags = story.get("tags", [])
            date = None
            pub = story.get("published_at", "")
            if pub:
                date = pub[:10]

            yield {
                "title": title,
                "text": text,
                "url": story.get("url", url),
                "date": date,
                "instrument_type": self._classify_instrument(title, tags),
                "tags": tags,
                "slug": story.get("slug", ""),
                "language": story.get("language", "EN"),
            }
            count += 1

        logger.info(f"Pressroom communiqués fetched: {count}")

        # 2. Legal library PDFs (if pdfplumber available)
        if HAS_PDFPLUMBER:
            for doc in LEGAL_LIBRARY_DOCS:
                logger.info(f"Fetching library PDF: {doc['title'][:60]}...")
                time.sleep(2)
                try:
                    text = self._fetch_pdf_text(doc["url"])
                    if text and len(text) >= 200:
                        yield {
                            "title": doc["title"],
                            "text": text,
                            "url": doc["url"],
                            "date": doc.get("date"),
                            "instrument_type": doc.get("instrument_type", "document"),
                            "tags": [],
                            "slug": "",
                            "language": "EN",
                        }
                        count += 1
                    else:
                        logger.warning(f"Insufficient PDF text for {doc['title'][:50]}")
                except Exception as e:
                    logger.error(f"Failed PDF fetch {doc['title'][:50]}: {e}")
        else:
            logger.info("pdfplumber not available; skipping legal library PDFs")

        logger.info(f"Total documents fetched: {count}")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Re-fetch all (small corpus)."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Normalize a raw document to standard schema."""
        text = raw.get("text", "")
        if not text or len(text) < 100:
            return None

        title = raw.get("title", "")
        url = raw.get("url", "")
        instrument_type = raw.get("instrument_type", "communiqué")
        date = raw.get("date")

        return {
            "_id": self._make_id(url),
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url,
            "instrument_type": instrument_type,
            "organization": "OECS",
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/OECS-LegalInstruments Data Fetcher")
    subparsers = parser.add_subparsers(dest="command")

    boot = subparsers.add_parser("bootstrap", help="Fetch data")
    boot.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast", help="Alias for bootstrap --full")

    args = parser.parse_args()

    scraper = OECSLegalInstrumentsScraper()

    if args.command == "bootstrap":
        if args.sample:
            stats = scraper.bootstrap(sample_mode=True, sample_size=15)
        elif args.full:
            stats = scraper.bootstrap(sample_mode=False)
        else:
            parser.print_help()
            return
        print(json.dumps(stats, indent=2))
    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap(sample_mode=False)
        print(json.dumps(stats, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
