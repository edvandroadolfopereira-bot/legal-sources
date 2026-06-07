#!/usr/bin/env python3
"""
DO/MedioAmbiente -- Ministerio de Medio Ambiente y Recursos Naturales
(Dominican Republic)

Fetches the full text of Dominican environmental legislation: leyes,
decretos, normas ambientales, resoluciones, and políticas from the
ministry's official website.

Strategy:
  ambiente.gob.do is a WordPress site using the WP File Download plugin.
  Two listing pages contain all documents as PDF links:
    /regulaciones/          (~23 recent regulations/policies)
    /sobre-nosotros/marco-legal (~89 laws, decrees, norms)
  Each <a class="wpfd_downloadlink"> carries a title attribute and an
  href to the PDF. We scrape both pages, deduplicate by URL, download
  each PDF, and extract text with pdfplumber.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import re
import io
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Dict

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.DO.MedioAmbiente")

SOURCE_ID = "DO/MedioAmbiente"
BASE_URL = "https://ambiente.gob.do"
MIN_TEXT_CHARS = 200

LISTING_PAGES = [
    "/regulaciones/",
    "/sobre-nosotros/marco-legal",
]

# Regex to extract WPFD download links with title attributes.
WPFD_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*wpfd_downloadlink[^"]*"[^>]*'
    r'href="([^"]+\.pdf)"[^>]*'
    r'title="([^"]*)"',
    re.I,
)

# Also match reverse order (title before href).
WPFD_LINK_RE2 = re.compile(
    r'<a[^>]*class="[^"]*wpfd_downloadlink[^"]*"[^>]*'
    r'title="([^"]*)"[^>]*'
    r'href="([^"]+\.pdf)"',
    re.I,
)

# Category mapping from URL path segments.
CATEGORY_MAP = {
    "leyes": "ley",
    "decretos": "decreto",
    "normas": "norma",
    "politicas-medioambientales": "politica",
    "2025": "regulacion",  # /regulaciones/ uses year-based paths
}

# Spanish months for date parsing.
MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

DATE_TEXT_RE = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(MONTHS_ES) + r")\s+de[l]?\s+(\d{4})", re.I
)


def extract_pdf_text(content: bytes) -> str:
    """Extract all text from a PDF using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


def clean_text(text: str) -> str:
    """Normalize whitespace and fix common PDF extraction artifacts."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def categorize_url(url: str) -> str:
    """Derive document category from the URL path."""
    for key, cat in CATEGORY_MAP.items():
        if f"/{key}/" in url:
            return cat
    return "regulacion"


def extract_date_from_title(title: str) -> Optional[str]:
    """Try to extract a year or date from the document title."""
    # Match patterns like "Ley No. 64-00" -> year 2000
    m = re.search(r"[-/](\d{2})(?:\s|$|\.)", title)
    if m:
        yy = int(m.group(1))
        year = 1900 + yy if yy >= 30 else 2000 + yy
        return f"{year}-01-01"
    # Match 4-digit year
    m = re.search(r"\b(19\d{2}|20\d{2})\b", title)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract the first dateline from the document body."""
    for m in DATE_TEXT_RE.finditer(text[:3000]):
        try:
            d = datetime(int(m.group(3)), MONTHS_ES[m.group(2).lower()],
                         int(m.group(1)))
            return d.strftime("%Y-%m-%d")
        except (ValueError, KeyError):
            continue
    return None


class MedioAmbienteScraper(BaseScraper):
    """
    Scraper for DO/MedioAmbiente — Ministerio de Medio Ambiente y
    Recursos Naturales (Dominican Republic).
    Country: DO
    URL: https://ambiente.gob.do/
    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LegalDataHunter/1.0 "
                          "(research; https://github.com/ZachLaik/LegalDataHunter)",
        })

    def _discover(self) -> List[Dict]:
        """Scrape both listing pages for WPFD download links."""
        seen: Dict[str, Dict] = {}

        for page_path in LISTING_PAGES:
            url = BASE_URL + page_path
            try:
                r = self.session.get(url, timeout=60)
                if r.status_code != 200:
                    logger.warning(f"{page_path}: HTTP {r.status_code}")
                    continue
            except Exception as e:
                logger.warning(f"{page_path} failed: {e}")
                continue

            html = r.text
            new = 0

            # Extract links (href before title).
            for href, title in WPFD_LINK_RE.findall(html):
                if "{{" in href:
                    continue  # Skip template placeholders
                key = href.lower()
                if key not in seen:
                    seen[key] = {"url": href, "title": title.strip()}
                    new += 1

            # Extract links (title before href).
            for title, href in WPFD_LINK_RE2.findall(html):
                if "{{" in href:
                    continue
                key = href.lower()
                if key not in seen:
                    seen[key] = {"url": href, "title": title.strip()}
                    new += 1

            logger.info(f"{page_path}: {new} new links (total {len(seen)})")

        entries = list(seen.values())
        logger.info(f"Discovered {len(entries)} unique PDF documents")
        return entries

    def fetch_all(self) -> Generator[dict, None, None]:
        """Download and extract text from all discovered PDFs."""
        entries = self._discover()
        for i, entry in enumerate(entries):
            url = entry["url"]
            title = entry["title"]
            category = categorize_url(url)

            logger.info(f"[{i+1}/{len(entries)}] {title}")

            try:
                self.rate_limiter.wait()
                r = self.session.get(url, timeout=120)
                if r.status_code != 200:
                    logger.warning(f"  HTTP {r.status_code}, skipping")
                    continue
                if len(r.content) < 100:
                    logger.warning(f"  Tiny response ({len(r.content)} bytes), skipping")
                    continue
            except Exception as e:
                logger.warning(f"  Download failed: {e}")
                continue

            text = clean_text(extract_pdf_text(r.content))
            if len(text) < MIN_TEXT_CHARS:
                logger.warning(f"  Insufficient text: {len(text)} chars")
                continue

            # Determine date
            date = extract_date_from_text(text) or extract_date_from_title(title)

            doc_id = hashlib.sha256(url.encode()).hexdigest()[:16]

            yield {
                "_id": doc_id,
                "_source": SOURCE_ID,
                "_type": "legislation",
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "text": text,
                "date": date,
                "url": url,
                "category": category,
                "pdf_size_bytes": len(r.content),
            }

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """For a mostly-static corpus, re-fetch all."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        return raw


def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="DO/MedioAmbiente bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Fetch all documents")
    boot.add_argument("--sample", action="store_true",
                       help="Fetch 15 samples only")
    boot.add_argument("--full", action="store_true",
                       help="Fetch all documents")

    sub.add_parser("bootstrap-fast", help="Alias for bootstrap --sample")
    sub.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = MedioAmbienteScraper()

    if args.command == "test":
        r = scraper.session.get(BASE_URL + "/regulaciones/", timeout=30)
        print(f"HTTP {r.status_code}, {len(r.text)} bytes")
        sys.exit(0 if r.status_code == 200 else 1)

    sample_mode = args.command == "bootstrap-fast" or (
        args.command == "bootstrap" and args.sample)
    limit = 15 if sample_mode else None

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    total_chars = 0
    for record in scraper.fetch_all():
        count += 1
        total_chars += len(record.get("text", ""))

        out = sample_dir / f"{record['_id']}.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        logger.info(f"  Saved {out.name}  ({len(record['text']):,} chars)")

        if limit and count >= limit:
            break

    print(f"\n{'='*60}")
    print(f"DO/MedioAmbiente: {count} records, {total_chars:,} total chars")
    print(f"Average: {total_chars // max(count, 1):,} chars/record")
    print(f"{'='*60}")

    if count == 0:
        logger.error("No records fetched!")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
