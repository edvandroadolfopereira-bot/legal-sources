#!/usr/bin/env python3
"""
INTL/GlobalHealthRightsDB — Global Health & Human Rights Database

Fetches health-related human rights case law from globalhealthrights.org.

Strategy:
  - Parse WordPress sitemap to get all ~1,450 case URLs
  - Fetch each case page and extract structured metadata + summary text
  - Text includes facts, decision/reasoning, key excerpts (typically 1,000-5,000 words)

Data:
  - ~1,450 cases from 122 countries
  - Languages: English (summaries), with some original-language judgments
  - License: Open access academic database (Georgetown University)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
"""

import argparse
import html
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.globalhealthrights.org"
SITEMAP_URL = f"{BASE_URL}/wp-sitemap-posts-post-1.xml"
SOURCE_ID = "INTL/GlobalHealthRightsDB"
SAMPLE_DIR = Path(__file__).parent / "sample"
REQUEST_DELAY = 2.0


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags and extract plain text."""

    def __init__(self):
        super().__init__()
        self._pieces: List[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag in ("br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table"):
            self._pieces.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._pieces.append(data)

    def get_text(self) -> str:
        raw = "".join(self._pieces)
        lines = [line.strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def strip_html(html_content: str) -> str:
    decoded = html.unescape(html_content)
    extractor = _HTMLTextExtractor()
    extractor.feed(decoded)
    return extractor.get_text()


class GlobalHealthRightsDBFetcher:
    """Fetcher for Global Health & Human Rights Database."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        })

    def _get(self, url: str) -> Optional[str]:
        """Fetch a URL with retry logic."""
        time.sleep(REQUEST_DELAY)
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if attempt < 2:
                    logger.warning("Retry %d for %s: %s", attempt + 1, url, e)
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.error("Failed to fetch %s: %s", url, e)
                    return None

    def _get_case_urls(self) -> List[str]:
        """Parse the WordPress sitemap to get all case page URLs."""
        logger.info("Fetching sitemap: %s", SITEMAP_URL)
        xml_text = self._get(SITEMAP_URL)
        if not xml_text:
            return []

        urls = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for url_elem in root.findall(".//sm:url/sm:loc", ns):
                if url_elem.text:
                    urls.append(url_elem.text.strip())
        except ET.ParseError as e:
            logger.error("Failed to parse sitemap XML: %s", e)
            return []

        # Filter out non-case pages (category pages, about pages, etc.)
        case_urls = []
        skip_prefixes = [
            "/category/", "/health-topics/", "/human-rights/", "/all-countries/",
            "/instruments/", "/constitutions/", "/about-the-database/",
            "/how-to-use-the-database/", "/resources/", "/blog/",
            "/advanced-search/", "/tag/", "/wp-",
        ]
        for url in urls:
            path = url.replace(BASE_URL, "")
            if any(path.startswith(p) for p in skip_prefixes):
                continue
            if path in ("/", ""):
                continue
            case_urls.append(url)

        logger.info("Found %d case URLs in sitemap (filtered from %d total)", len(case_urls), len(urls))
        return case_urls

    def _parse_case_page(self, html_text: str, url: str) -> Optional[Dict[str, Any]]:
        """Extract structured data from a case detail page."""
        # Extract title
        title = ""
        m = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html_text, re.DOTALL)
        if not m:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.DOTALL)
        if m:
            title = strip_html(m.group(1)).strip()

        if not title:
            return None

        # Extract metadata fields
        metadata = {}

        # Citation from dedicated div
        m = re.search(r'<div class="citation[^"]*">(.*?)</div>', html_text, re.DOTALL)
        if m:
            metadata["citation"] = strip_html(m.group(1)).strip()

        # Fields follow pattern: <b>Field</b>: <a href="...">Value</a> or <b>Field</b>: Value
        field_patterns = {
            "country": r'<b>Country</b>\s*:\s*(?:<a[^>]*>)?\s*([^<\n]+)',
            "court": r'<b>Court</b>\s*:\s*(?:<a[^>]*>)?\s*([^<\n]+)',
            "year": r'<b>Year</b>\s*:\s*(?:<a[^>]*>)?\s*(\d{4})',
        }
        fallback_patterns = {
            "country": r'Country\s*:\s*([^<\n]+)',
            "court": r'Court\s*:\s*([^<\n]+)',
            "year": r'Year\s*:\s*(\d{4})',
        }

        for field, pattern in field_patterns.items():
            if field not in metadata:
                m = re.search(pattern, html_text, re.IGNORECASE)
                if m:
                    metadata[field] = strip_html(m.group(1)).strip()
        for field, pattern in fallback_patterns.items():
            if field not in metadata:
                m = re.search(pattern, html_text, re.IGNORECASE)
                if m:
                    metadata[field] = strip_html(m.group(1)).strip()

        # Try extracting year from title if not in metadata
        if "year" not in metadata:
            m = re.search(r'\b(19\d{2}|20\d{2})\b', title)
            if m:
                metadata["year"] = m.group(1)

        # Extract the main content area
        # Find the entry-content div and extract until the end markers
        content_text = ""
        start = html_text.find('<div class="entry entry-content">')
        if start < 0:
            start = html_text.find('entry-content')
            if start >= 0:
                # Find the opening div tag
                start = html_text.rfind('<div', max(0, start - 100), start)

        if start >= 0:
            # Find the end of the content section
            end_markers = ['<div class="printfooter"', '<footer', '<div id="comments"',
                           '<div class="post-navigation"', '</main>']
            end = len(html_text)
            for marker in end_markers:
                idx = html_text.find(marker, start)
                if 0 < idx < end:
                    end = idx
            content_html = html_text[start:end]
            content_text = strip_html(content_html)

        # Extract health topics and human rights categories
        health_topics = []
        hr_categories = []
        for m in re.finditer(r'/health-topics/([^/"]+)/', html_text):
            topic = m.group(1).replace("-", " ").title()
            if topic not in health_topics:
                health_topics.append(topic)
        for m in re.finditer(r'/human-rights/([^/"]+)/', html_text):
            right = m.group(1).replace("-", " ").title()
            if right not in hr_categories:
                hr_categories.append(right)

        return {
            "title": title,
            "text": content_text,
            "country": metadata.get("country", ""),
            "court": metadata.get("court", ""),
            "citation": metadata.get("citation", ""),
            "year": metadata.get("year", ""),
            "health_topics": health_topics[:10],
            "human_rights": hr_categories[:10],
        }

    def normalize(self, parsed: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
        """Normalize a parsed case into a standard record."""
        text = parsed.get("text", "")
        if not text or len(text) < 100:
            return None

        slug = url.rstrip("/").split("/")[-1]
        doc_id = f"GHRDB-{slug[:80]}"
        year = parsed.get("year", "")
        date = f"{year}-01-01" if year else None

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": parsed["title"],
            "text": text,
            "date": date,
            "url": url,
            "country": parsed.get("country", ""),
            "court": parsed.get("court", ""),
            "citation": parsed.get("citation", ""),
            "health_topics": parsed.get("health_topics", []),
            "human_rights": parsed.get("human_rights", []),
        }

    def fetch_all(self, sample: bool = False, max_docs: int = 15) -> Iterator[Dict[str, Any]]:
        """Yield all cases from the database."""
        case_urls = self._get_case_urls()
        if not case_urls:
            logger.error("No case URLs found in sitemap!")
            return

        count = 0
        errors = 0
        for i, url in enumerate(case_urls):
            page_html = self._get(url)
            if not page_html:
                errors += 1
                continue

            parsed = self._parse_case_page(page_html, url)
            if not parsed:
                errors += 1
                continue

            doc = self.normalize(parsed, url)
            if doc:
                count += 1
                yield doc

            if sample and count >= max_docs:
                logger.info("Sample limit reached (%d docs)", max_docs)
                return

            if (i + 1) % 50 == 0:
                logger.info("Progress: %d/%d URLs processed, %d docs yielded, %d errors",
                            i + 1, len(case_urls), count, errors)

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield cases from the database (no date filtering available — returns all)."""
        yield from self.fetch_all()


def bootstrap(sample: bool = False, full: bool = False, since: Optional[str] = None):
    """Main entry point."""
    fetcher = GlobalHealthRightsDBFetcher()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    if since:
        docs = fetcher.fetch_updates(since)
    else:
        docs = fetcher.fetch_all(sample=sample)

    count = 0
    for doc in docs:
        count += 1
        text_len = len(doc.get("text", ""))
        logger.info("  → %s | text=%d chars | country=%s", doc["title"][:70], text_len, doc.get("country"))

        if sample:
            sample_path = SAMPLE_DIR / f"{doc['_id']}.json"
            with open(sample_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)

    logger.info("Done: %d cases fetched", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="INTL/GlobalHealthRightsDB bootstrap")
    parser.add_argument("command", choices=["bootstrap"], help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Save sample records")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    parser.add_argument("--since", type=str, help="Fetch updates since date (ISO 8601)")
    args = parser.parse_args()

    if args.command == "bootstrap":
        count = bootstrap(sample=args.sample, full=args.full, since=args.since)
        if count == 0:
            logger.error("No records fetched!")
            sys.exit(1)
