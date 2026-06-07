#!/usr/bin/env python3
"""
AO/LexAO -- Lex.ao Free Angolan Legal Platform

Fetches Angolan legislation from lex.ao, a Docusaurus-based legal portal
with 1,200+ documents from the National Assembly, People's Assembly, and
regulatory agencies.

Strategy:
  - Parse sitemap.xml to enumerate all /docs/ URLs
  - Fetch each document page and extract text from HTML
  - Extract metadata from URL pattern and page content

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Re-fetch all
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import re
import json
import logging
import time
import html
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AO.LexAO")

BASE_URL = "https://lex.ao"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

MIN_TEXT_CHARS = 200

# Map slug prefixes to readable institution names
INSTITUTION_MAP = {
    "assembleia-nacional": "Assembleia Nacional",
    "assembleia-do-povo": "Assembleia do Povo",
    "agencia-angolana-de-regulacao-e-supervisao-de-seguros": "AARSEG",
    "agencia-nacional-de-petroleo-gas-e-biocombustiveis": "ANPG",
}

# Map document type prefixes in slug to types
DOC_TYPE_MAP = {
    "lei-": "Lei",
    "decreto-presidencial-": "Decreto Presidencial",
    "decreto-legislativo-presidencial-": "Decreto Legislativo Presidencial",
    "decreto-executivo-": "Decreto Executivo",
    "decreto-": "Decreto",
    "resolucao-": "Resolução",
    "aviso-": "Aviso",
    "norma-regulamentar-": "Norma Regulamentar",
    "instrutivo-": "Instrutivo",
    "despacho-": "Despacho",
    "directiva-": "Directiva",
}


def _fetch_url(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a URL and return the response body as text."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def _parse_sitemap(xml_text: str) -> List[str]:
    """Extract all /docs/ URLs from sitemap XML."""
    urls = []
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for url_el in root.findall("sm:url", ns):
        loc = url_el.find("sm:loc", ns)
        if loc is not None and loc.text and "/docs/" in loc.text:
            urls.append(loc.text.strip())
    return urls


def _extract_metadata_from_url(url: str) -> Dict[str, Any]:
    """Extract institution, year, and document slug from URL."""
    # Pattern: /docs/{institution}/{year}/{document-slug}/
    match = re.search(r"/docs/([^/]+)/(\d{4})/([^/]+)/?$", url)
    if not match:
        return {"institution_slug": "", "year": "", "doc_slug": ""}
    return {
        "institution_slug": match.group(1),
        "year": match.group(2),
        "doc_slug": match.group(3),
    }


def _slug_to_title(slug: str) -> str:
    """Convert URL slug to a human-readable title."""
    # e.g. "lei-n-o-1-20-de-22-de-janeiro" -> "Lei n.º 1/20 de 22 de Janeiro"
    title = slug.replace("-", " ")
    # Fix "n o" -> "n.º"
    title = re.sub(r"\bn o\b", "n.º", title)
    # Capitalize first letter
    title = title[0].upper() + title[1:] if title else title
    return title


def _classify_doc_type(slug: str) -> str:
    """Determine document type from slug."""
    for prefix, dtype in DOC_TYPE_MAP.items():
        if slug.startswith(prefix):
            return dtype
    return "Outro"


def _strip_html(raw_html: str) -> str:
    """Strip HTML tags and decode entities to plain text."""
    text = re.sub(r"<br\s*/?>", "\n", raw_html)
    text = re.sub(r"</?p[^>]*>", "\n", text)
    text = re.sub(r"<li[^>]*>", "\n- ", text)
    text = re.sub(r"</?(?:ul|ol)[^>]*>", "\n", text)
    text = re.sub(r"<h[1-6][^>]*>", "\n## ", text)
    text = re.sub(r"</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_article_text(html_text: str) -> str:
    """Extract main content from Docusaurus page HTML."""
    # Try to find the main article content
    # Docusaurus uses <article> tag for main content
    article_match = re.search(
        r"<article[^>]*>(.*?)</article>", html_text, re.DOTALL
    )
    if article_match:
        return _strip_html(article_match.group(1))

    # Fallback: look for markdown content area
    main_match = re.search(
        r'<div[^>]*class="[^"]*markdown[^"]*"[^>]*>(.*?)</div>\s*</article',
        html_text,
        re.DOTALL,
    )
    if main_match:
        return _strip_html(main_match.group(1))

    # Last resort: extract from <main> tag
    main_match = re.search(r"<main[^>]*>(.*?)</main>", html_text, re.DOTALL)
    if main_match:
        return _strip_html(main_match.group(1))

    return ""


def _extract_title_from_html(html_text: str) -> Optional[str]:
    """Extract the page title from HTML."""
    # Try <h1> first
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
    if h1_match:
        return _strip_html(h1_match.group(1))
    # Try <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.DOTALL)
    if title_match:
        title = _strip_html(title_match.group(1))
        # Remove site suffix like " | LEX"
        title = re.sub(r"\s*\|\s*LEX.*$", "", title)
        return title
    return None


class AOLexAOScraper(BaseScraper):
    SOURCE_ID = "AO/LexAO"

    def __init__(self):
        source_dir = str(Path(__file__).resolve().parent)
        super().__init__(source_dir)

    def _get_doc_urls(self) -> List[str]:
        """Fetch sitemap and return all document URLs."""
        xml_text = _fetch_url(SITEMAP_URL)
        if not xml_text:
            logger.error("Failed to fetch sitemap.xml")
            return []
        urls = _parse_sitemap(xml_text)
        logger.info(f"Sitemap: found {len(urls)} document URLs")
        return urls

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all legislation documents."""
        urls = self._get_doc_urls()
        logger.info(f"Total documents to process: {len(urls)}")

        for i, url in enumerate(urls):
            meta = _extract_metadata_from_url(url)
            if not meta["doc_slug"]:
                continue

            institution_slug = meta["institution_slug"]
            year = meta["year"]
            doc_slug = meta["doc_slug"]
            doc_id = f"{institution_slug}_{year}_{doc_slug}"

            # Rate limit
            time.sleep(1)

            page_html = _fetch_url(url)
            if not page_html:
                logger.warning(f"Failed to fetch: {url}")
                continue

            # Extract text
            text = _extract_article_text(page_html)
            if len(text) < MIN_TEXT_CHARS:
                logger.warning(
                    f"Skipping {doc_slug}: insufficient text ({len(text)} chars)"
                )
                continue

            # Extract title
            title = _extract_title_from_html(page_html) or _slug_to_title(doc_slug)

            # Map institution
            institution = INSTITUTION_MAP.get(institution_slug, institution_slug)

            # Classify document type
            doc_type = _classify_doc_type(doc_slug)

            yield self.normalize({
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "url": url,
                "year": year,
                "institution": institution,
                "doc_type": doc_type,
            })

            if (i + 1) % 50 == 0:
                logger.info(f"Processed {i + 1}/{len(urls)} documents")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Re-fetch all (sitemap doesn't have lastmod granularity)."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw record into standard schema."""
        return {
            "_id": raw["doc_id"],
            "_source": self.SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("year"),
            "url": raw["url"],
            "institution": raw.get("institution", ""),
            "doc_type": raw.get("doc_type", ""),
        }


# --- CLI Entry Point ---

def main():
    import argparse

    parser = argparse.ArgumentParser(description="AO/LexAO bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch only 15 sample records")
    args = parser.parse_args()

    scraper = AOLexAOScraper()

    if args.command == "test":
        urls = scraper._get_doc_urls()
        print(f"OK: Found {len(urls)} documents in sitemap")
        if urls:
            print(f"Sample URL: {urls[0]}")
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    limit = 15 if args.sample else 9999

    for record in scraper.fetch_all():
        count += 1
        # Use doc_slug (last URL segment) for shorter, unique filenames
        slug = record["_id"].rsplit("_", 1)[-1] if "_" in record["_id"] else record["_id"]
        fname = re.sub(r'[^\w\-]', '_', slug)[:80] + ".json"
        with open(sample_dir / fname, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        text_len = len(record.get("text", ""))
        logger.info(f"[{count}] {record['title'][:60]} ({text_len} chars)")

        if count >= limit:
            logger.info(f"Sample limit reached ({limit} records)")
            break

    print(f"\nDone: {count} records saved to {sample_dir}")


if __name__ == "__main__":
    main()
