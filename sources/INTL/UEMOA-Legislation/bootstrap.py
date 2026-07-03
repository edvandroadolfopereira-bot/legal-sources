#!/usr/bin/env python3
"""
INTL/UEMOA-Legislation -- UEMOA Legal Instruments

Fetches legal instruments from the UEMOA e-docucenter portal:
  - Règlements (regulations)
  - Règlements d'exécution (implementing regulations)
  - Directives
  - Décisions (decisions)
  - Actes additionnels (additional acts)
  - Protocoles additionnels (additional protocols)

Strategy:
  - Fetch sitemap from e-docucenter.uemoa.int/fr/sitemap.xml
  - Filter URLs matching legal instrument patterns (ndeg = n°)
  - Scrape each page's <article> tag for full text
  - All documents are in French

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
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
logger = logging.getLogger("legal-data-hunter.INTL.UEMOA-Legislation")

SOURCE_ID = "INTL/UEMOA-Legislation"
BASE_URL = "https://e-docucenter.uemoa.int"
SITEMAP_URL = f"{BASE_URL}/fr/sitemap.xml"

# Patterns that identify numbered legal instruments in URL slugs
INSTRUMENT_PATTERNS = [
    (r"reglement-dexe?cution-ndeg", "reglement_execution"),
    (r"reglement-ndeg", "reglement"),
    (r"directive-ndeg", "directive"),
    (r"decision-ndeg", "decision"),
    (r"acte-additionnel-ndeg", "acte_additionnel"),
    (r"protocole-additionnel-ndeg", "protocole_additionnel"),
    (r"recommandation-ndeg", "recommandation"),
]

REQUEST_DELAY = 2  # seconds between requests
MAX_PDF_SIZE = 15 * 1024 * 1024  # 15 MB
MIN_INLINE_TEXT = 500  # chars; below this, try PDF instead
MIN_FINAL_TEXT = 400  # chars; skip record if final text is shorter


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities, preserving paragraph breaks."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


def classify_url(url: str) -> Optional[str]:
    """Classify a URL as a legal instrument type, or None if not a legal act."""
    path = url.split("/fr/")[-1] if "/fr/" in url else ""
    for pattern, instrument_type in INSTRUMENT_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return instrument_type
    return None


def _create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
        "Accept": "text/html,application/xhtml+xml,application/xml",
    })
    return session


class UEMOALegislationScraper(BaseScraper):
    """Scraper for INTL/UEMOA-Legislation."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = _create_session()

    def _get(self, url: str, timeout: int = 30) -> Optional[requests.Response]:
        """Fetch a URL with retry on connection drops."""
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=timeout, verify=False)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                wait = (attempt + 1) * 10
                logger.warning(f"Connection error (attempt {attempt+1}/3), waiting {wait}s: {e}")
                time.sleep(wait)
                self.session = _create_session()
            except requests.HTTPError as e:
                logger.error(f"HTTP error for {url}: {e}")
                return None
        logger.error(f"Failed after 3 attempts: {url}")
        return None

    def _fetch_sitemap_urls(self) -> list[tuple[str, str]]:
        """Fetch and parse sitemap, return list of (url, instrument_type)."""
        resp = self._get(SITEMAP_URL)
        if not resp:
            logger.error("Failed to fetch sitemap")
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse sitemap XML: {e}")
            return []

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [u.text for u in root.findall(".//s:url/s:loc", ns) if u.text]

        legal_acts = []
        for url in urls:
            instrument_type = classify_url(url)
            if instrument_type:
                legal_acts.append((url, instrument_type))

        logger.info(f"Sitemap: {len(urls)} total URLs, {len(legal_acts)} legal instruments")
        return legal_acts

    def _extract_article(self, html: str) -> tuple[str, str, list[str]]:
        """Extract title, text, and PDF URLs from an article page."""
        # Title: first <h1> or from <title>
        title = ""
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        if h1_match:
            title = strip_html(h1_match.group(1)).strip()

        if not title:
            title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
            if title_match:
                title = strip_html(title_match.group(1)).split("|")[0].strip()

        # Find PDF links
        pdf_urls = re.findall(r'href="(/sites/default/files/[^"]+\.pdf)"', html)
        pdf_urls = [f"{BASE_URL}{p}" for p in pdf_urls]

        # Text from <article> tag
        article_match = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL)
        if article_match:
            raw = article_match.group(1)
            text = strip_html(raw)
            # Remove the "Soumis par ... le ..." prefix
            text = re.sub(r"^Soumis par \S+ le \S+\s*", "", text)
            return title, text.strip(), pdf_urls

        # Fallback: try field--name-body
        body_match = re.search(
            r'class="[^"]*field--name-body[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL
        )
        if body_match:
            text = strip_html(body_match.group(1))
            return title, text.strip(), pdf_urls

        return title, "", pdf_urls

    def _extract_pdf_text(self, url: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        if not HAS_PDFPLUMBER:
            logger.warning("pdfplumber not available, cannot extract PDF text")
            return None

        resp = self._get(url, timeout=90)
        if not resp:
            return None

        if len(resp.content) > MAX_PDF_SIZE:
            logger.warning(f"PDF too large ({len(resp.content)} bytes): {url}")
            return None

        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass

                text = "\n\n".join(pages_text)
                if len(text) < 100:
                    logger.warning(f"PDF text too short ({len(text)} chars, likely scanned): {url}")
                    return None
                return text

        except Exception as e:
            logger.error(f"PDF extraction failed for {url}: {e}")
            return None

    def _make_id(self, url: str, instrument_type: str) -> str:
        """Generate a stable ID from the URL slug."""
        slug = url.rstrip("/").split("/")[-1]
        slug = re.sub(r"[^a-z0-9-]", "", slug.lower())
        return f"uemoa-{slug}"[:120]

    def _parse_date_from_text(self, text: str) -> Optional[str]:
        """Try to extract a date from the document text."""
        # Common French date patterns in UEMOA acts
        months = {
            "janvier": "01", "février": "02", "mars": "03",
            "avril": "04", "mai": "05", "juin": "06",
            "juillet": "07", "août": "08", "septembre": "09",
            "octobre": "10", "novembre": "11", "décembre": "12",
        }
        pattern = r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})"
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Use the last date found (usually the signing date)
            day, month_name, year = matches[-1]
            month = months.get(month_name.lower())
            if month:
                return f"{year}-{month}-{int(day):02d}"
        return None

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all UEMOA legal instruments."""
        legal_acts = self._fetch_sitemap_urls()
        if not legal_acts:
            logger.error("No legal instrument URLs found")
            return

        count = 0
        seen_ids = set()

        for url, instrument_type in legal_acts:
            if sample and count >= 15:
                return

            time.sleep(REQUEST_DELAY)
            resp = self._get(url)
            if not resp:
                logger.warning(f"Failed to fetch: {url}")
                continue

            title, text, pdf_urls = self._extract_article(resp.text)

            # If inline text is too short, try extracting from PDF
            if len(text) < MIN_INLINE_TEXT and pdf_urls:
                logger.info(f"Inline text short ({len(text)} chars), trying PDF: {pdf_urls[0]}")
                time.sleep(REQUEST_DELAY)
                pdf_text = self._extract_pdf_text(pdf_urls[0])
                if pdf_text and len(pdf_text) > len(text):
                    text = pdf_text

            # Clean navigation/template junk from text
            text = re.sub(r"Liens transversaux de livre pour .*$", "", text, flags=re.MULTILINE).strip()
            text = re.sub(r"Télécharger [\w\s]+\n", "", text).strip()
            text = re.sub(r"\S+\.pdf\s*\(\d+[\.,]\d+\s*Ko\)", "", text).strip()

            if not text or len(text) < MIN_FINAL_TEXT:
                logger.warning(f"Insufficient text ({len(text)} chars): {url}")
                continue

            doc_id = self._make_id(url, instrument_type)
            if doc_id in seen_ids:
                logger.info(f"Skipping duplicate: {doc_id}")
                continue
            seen_ids.add(doc_id)

            # Use title from text if H1 was empty
            if not title and text:
                # First line is often the title in uppercase
                first_line = text.split("\n")[0].strip()
                if len(first_line) < 300:
                    title = first_line

            date = self._parse_date_from_text(text)

            record = {
                "_id": doc_id,
                "_source": SOURCE_ID,
                "_type": "legislation",
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": title or doc_id,
                "text": text,
                "date": date,
                "url": url,
                "instrument_type": instrument_type,
            }

            yield record
            count += 1
            logger.info(f"[{count}] {title[:60]}... ({len(text)} chars)")

        logger.info(f"Completed: {count} records")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """UEMOA documents are rarely updated; full refresh is preferred."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Records are already normalized during fetch."""
        return raw


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/UEMOA-Legislation bootstrap")
    subparsers = parser.add_subparsers(dest="command")

    boot_parser = subparsers.add_parser("bootstrap")
    boot_parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot_parser.add_argument("--full", action="store_true", help="Full fetch")

    subparsers.add_parser("bootstrap-fast")

    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample = getattr(args, "sample", False) and args.command != "bootstrap-fast"
        full = getattr(args, "full", False) or args.command == "bootstrap-fast"

        scraper = UEMOALegislationScraper()
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        records = []
        for record in scraper.fetch_all(sample=not full):
            records.append(record)
            fname = re.sub(r"[^a-z0-9_-]", "_", record["_id"][:60]) + ".json"
            out_path = sample_dir / fname
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(records)} records to {sample_dir}")

        texts = [r for r in records if r.get("text") and len(r["text"]) > 100]
        if texts:
            avg_len = sum(len(r["text"]) for r in texts) // len(texts)
            logger.info(f"Records with text: {len(texts)}/{len(records)}, avg {avg_len} chars")
        else:
            logger.warning("No records with substantial text content!")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
