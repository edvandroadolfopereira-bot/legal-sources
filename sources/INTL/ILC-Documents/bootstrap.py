#!/usr/bin/env python3
"""
INTL/ILC-Documents -- UN International Law Commission Draft Articles & Reports

Fetches ILC final texts (draft articles, commentaries, conventions) from
legal.un.org/ilc/ with full text extracted from PDFs.

Strategy:
  - Scrape texts/texts.shtml for the master topic list (~50 topics)
  - For each topic page, extract PDF URLs for draft articles, commentaries,
    and conventions
  - Download PDFs and extract full text via pdfplumber
  - ~100-150 documents total (draft articles + commentaries + conventions)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin

import requests
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.ILC-Documents")

BASE_URL = "https://legal.un.org"
TEXTS_URL = f"{BASE_URL}/ilc/texts/texts.shtml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

# Topic category names by prefix
CATEGORY_MAP = {
    "1": "Sources of International Law",
    "2": "Subjects of International Law",
    "3": "Succession of States",
    "4": "State Jurisdiction / Immunity",
    "5": "Law of International Organizations",
    "6": "Position of the Individual",
    "7": "International Criminal Law",
    "8": "Law of International Spaces",
    "9": "Law of International Relations",
    "10": "Settlement of Disputes",
}


class ILCDocumentsScraper(BaseScraper):
    SOURCE_ID = "INTL/ILC-Documents"

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch_page(self, url: str) -> Optional[str]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if attempt == 2:
                    logger.warning("Failed to fetch %s: %s", url, e)
                    return None
                time.sleep(2 * (attempt + 1))

    def _download_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract text via pdfplumber."""
        for attempt in range(3):
            try:
                resp = self.session.get(pdf_url, timeout=120)
                resp.raise_for_status()
                pdf_bytes = io.BytesIO(resp.content)
                pages_text = []
                with pdfplumber.open(pdf_bytes) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            pages_text.append(text)
                        try:
                            page.flush_cache(); page.get_textmap.cache_clear()
                        except Exception:
                            pass
                full_text = "\n\n".join(pages_text)
                return full_text if full_text.strip() else None
            except Exception as e:
                if attempt == 2:
                    logger.warning("PDF extraction failed for %s: %s", pdf_url, e)
                    return None
                time.sleep(2 * (attempt + 1))

    def _discover_topics(self) -> List[Dict]:
        """Parse texts.shtml to discover all topic page links."""
        from bs4 import BeautifulSoup

        html = self._fetch_page(TEXTS_URL)
        if not html:
            logger.error("Cannot fetch ILC texts index")
            return []

        soup = BeautifulSoup(html, "html.parser")
        topics = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Match topic page links like 9_6.shtml, 1_1.shtml, etc.
            match = re.match(r'^(\d+_\d+(?:_part_\w+)?)\.(shtml|htm)$', href)
            if not match:
                # Also match just "9.shtml" pattern
                match = re.match(r'^(\d+)\.(shtml|htm)$', href)
            if not match:
                continue

            topic_id = match.group(1)
            if topic_id in seen:
                continue
            seen.add(topic_id)

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Determine category from topic_id prefix
            prefix = topic_id.split("_")[0]
            category = CATEGORY_MAP.get(prefix, "Other")

            topic_url = urljoin(TEXTS_URL, href)
            topics.append({
                "topic_id": topic_id,
                "title": title,
                "url": topic_url,
                "category": category,
            })

        logger.info("Discovered %d ILC topics", len(topics))
        return topics

    def _extract_documents_from_topic(self, topic: Dict) -> List[Dict]:
        """Extract PDF document URLs from a topic page."""
        from bs4 import BeautifulSoup

        self.rate_limiter.wait()
        html = self._fetch_page(topic["url"])
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Decode HTML entities
            href = href.replace("&amp;", "&")

            # Match PDF links for draft articles, commentaries, conventions
            if ".pdf" not in href.lower():
                continue
            # Skip the ILC statute PDF
            if "statute" in href.lower():
                continue

            # Determine document type from path
            doc_type = "other"
            if "draft_articles" in href:
                doc_type = "draft_articles"
            elif "commentaries" in href:
                doc_type = "commentaries"
            elif "conventions" in href:
                doc_type = "convention"
            elif "draft_conclusions" in href:
                doc_type = "draft_conclusions"
            elif "guiding_principles" in href:
                doc_type = "guiding_principles"
            elif "model_rules" in href:
                doc_type = "model_rules"

            # Build full URL
            if href.startswith("http"):
                # Some links go through docs/?path=... redirect
                if "docs/?path=" in href:
                    # Extract the actual path
                    path_match = re.search(r'path=\.\.(/ilc/[^&]+\.pdf)', href)
                    if path_match:
                        pdf_url = f"{BASE_URL}{path_match.group(1)}"
                    else:
                        pdf_url = href
                else:
                    pdf_url = href
            elif href.startswith("instruments/"):
                pdf_url = f"{BASE_URL}/ilc/texts/{href}"
            elif href.startswith("../"):
                pdf_url = urljoin(topic["url"], href)
            else:
                pdf_url = urljoin(topic["url"], href)

            # Extract year from filename
            year_match = re.search(r'(\d{4})\.pdf', pdf_url)
            year = year_match.group(1) if year_match else None

            link_text = link.get_text(strip=True)

            documents.append({
                "pdf_url": pdf_url,
                "doc_type": doc_type,
                "year": year,
                "link_text": link_text,
                "topic_id": topic["topic_id"],
                "topic_title": topic["title"],
                "category": topic["category"],
                "topic_url": topic["url"],
            })

        return documents

    def test_connection(self) -> bool:
        try:
            html = self._fetch_page(TEXTS_URL)
            if html and "International Law Commission" in html:
                logger.info("Connection OK: ILC texts index accessible")
                return True
            return False
        except Exception as e:
            logger.error("Connection failed: %s", e)
            return False

    def fetch_all(self) -> Generator[Dict, None, None]:
        topics = self._discover_topics()
        logger.info("Processing %d ILC topics...", len(topics))

        seen_pdfs = set()
        for i, topic in enumerate(topics):
            logger.info("[%d/%d] Topic: %s", i + 1, len(topics), topic["title"][:70])
            documents = self._extract_documents_from_topic(topic)

            for doc in documents:
                pdf_url = doc["pdf_url"]
                if pdf_url in seen_pdfs:
                    continue
                seen_pdfs.add(pdf_url)

                logger.info("  Downloading: %s (%s)", pdf_url.split("/")[-1], doc["doc_type"])
                self.rate_limiter.wait()
                text = self._download_pdf_text(pdf_url)

                if not text or len(text) < 100:
                    logger.warning("  Skipping (insufficient text): %s", pdf_url)
                    continue

                # Build title
                type_label = doc["doc_type"].replace("_", " ").title()
                title = f"{doc['topic_title']} — {type_label}"
                if doc["year"]:
                    title += f" ({doc['year']})"

                yield {
                    "title": title,
                    "text": text,
                    "url": doc["topic_url"],
                    "pdf_url": pdf_url,
                    "doc_type": doc["doc_type"],
                    "topic_id": doc["topic_id"],
                    "topic_title": doc["topic_title"],
                    "category": doc["category"],
                    "year": doc["year"],
                    "link_text": doc.get("link_text", ""),
                }

    def fetch_updates(self, since: datetime) -> Generator[Dict, None, None]:
        return
        yield

    def normalize(self, raw: dict) -> dict:
        topic_id = raw["topic_id"]
        doc_type = raw["doc_type"]
        year = raw.get("year", "unknown")
        safe_id = f"ILC-{topic_id}-{doc_type}-{year}"
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', safe_id)

        date_str = f"{year}-01-01" if year and year != "unknown" else None

        return {
            "_id": safe_id,
            "_source": "INTL/ILC-Documents",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": date_str,
            "url": raw["url"],
            "pdf_url": raw["pdf_url"],
            "document_type": raw["doc_type"],
            "topic_id": raw["topic_id"],
            "topic_title": raw["topic_title"],
            "topic_category": raw["category"],
        }

    def run_bootstrap(self, sample: bool = False):
        sample_dir = self.source_dir / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for raw in self.fetch_all():
            normalized = self.normalize(raw)
            fname = re.sub(r'[^\w\-.]', '_', f"{normalized['_id'][:80]}.json")
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            count += 1
            logger.info("  -> %s: %d chars of text", normalized["_id"], len(normalized["text"]))

            if sample and count >= 15:
                break

        logger.info("Bootstrap complete: %d records saved", count)
        return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/ILC-Documents Bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = ILCDocumentsScraper()

    if args.command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        sample = args.sample or args.command == "bootstrap-fast"
        scraper.run_bootstrap(sample=sample)
    elif args.command == "update":
        logger.info("No update mechanism (ILC texts rarely change)")


if __name__ == "__main__":
    main()
