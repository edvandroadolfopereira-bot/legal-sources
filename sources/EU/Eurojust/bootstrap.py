#!/usr/bin/env python3
"""
Eurojust — Case Law Analysis & Judicial Cooperation Reports

Scrapes ~70 publications from:
  https://www.eurojust.europa.eu/term/case-law-analysis

Each publication page links to a PDF. Full text is extracted via pdfplumber.
"""

import hashlib
import io
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.eurojust.europa.eu"
LISTING_URL = f"{BASE_URL}/term/case-law-analysis"


class EurojustFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    # Month name → number mapping for date parsing
    MONTHS = {
        "January": "01", "February": "02", "March": "03", "April": "04",
        "May": "05", "June": "06", "July": "07", "August": "08",
        "September": "09", "October": "10", "November": "11", "December": "12",
    }

    def _parse_listing_date(self, text: str) -> Optional[str]:
        """Extract date from listing text like '20 November 2025'."""
        m = re.search(
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(\d{4})", text
        )
        if m:
            day, month, year = m.group(1), m.group(2), m.group(3)
            return f"{year}-{self.MONTHS[month]}-{int(day):02d}"
        return None

    def _get_listing_pages(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """Scrape the paginated listing to discover all publications."""
        publications = []
        for page_num in range(max_pages):
            url = f"{LISTING_URL}?page={page_num}"
            logger.info(f"Fetching listing page {page_num}: {url}")
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"Error fetching listing page {page_num}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find publication links — they appear in the main content area
            found_on_page = 0
            for link in soup.select("a[href]"):
                href = link.get("href", "")
                if "/publication/" not in href:
                    continue
                title_text = link.get_text(strip=True)
                if not title_text or len(title_text) < 10:
                    continue
                full_url = urljoin(BASE_URL, href)
                if any(p["url"] == full_url for p in publications):
                    continue

                # Try to extract date from the surrounding text
                parent = link.find_parent(["li", "div", "article"])
                date = None
                if parent:
                    date = self._parse_listing_date(parent.get_text())
                if not date:
                    date = self._parse_listing_date(resp.text[max(0, resp.text.find(href)-200):resp.text.find(href)+500])

                publications.append({"url": full_url, "title": title_text, "date": date})
                found_on_page += 1

            logger.info(f"  Found {found_on_page} publications on page {page_num}")
            if found_on_page == 0:
                break
            time.sleep(1.5)

        logger.info(f"Total publications discovered: {len(publications)}")
        return publications

    def _get_pdf_url_and_metadata(self, pub_url: str) -> Optional[Dict[str, Any]]:
        """Visit a publication page and extract the PDF download URL + metadata."""
        try:
            resp = self.session.get(pub_url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Error fetching publication page {pub_url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract date from meta tag or page content
        date = None
        date_meta = soup.find("meta", {"property": "article:published_time"})
        if date_meta and date_meta.get("content"):
            date = date_meta["content"][:10]
        if not date:
            # Try finding date in the page text
            time_elem = soup.find("time")
            if time_elem:
                date = time_elem.get("datetime", "")[:10] or time_elem.get_text(strip=True)

        # Extract description
        desc = ""
        desc_meta = soup.find("meta", {"name": "description"})
        if desc_meta:
            desc = desc_meta.get("content", "")

        # Find PDF download link
        pdf_url = None
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.endswith(".pdf") and "sites/default/files" in href:
                pdf_url = urljoin(BASE_URL, href)
                break

        # Extract ISBN/DOI if available
        isbn = ""
        doi = ""
        page_text = soup.get_text()
        isbn_match = re.search(r"ISBN[:\s]*([\d\-]+)", page_text)
        if isbn_match:
            isbn = isbn_match.group(1)
        doi_match = re.search(r"DOI[:\s]*([\d./\-]+)", page_text)
        if doi_match:
            doi = doi_match.group(1)

        return {
            "pdf_url": pdf_url,
            "date": date,
            "description": desc,
            "isbn": isbn,
            "doi": doi,
        }

    def _extract_text_from_pdf(self, pdf_url: str) -> Optional[str]:
        """Download PDF and extract text using pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=120, stream=True)
            resp.raise_for_status()
            # Check size — skip if > 50MB
            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length > 50 * 1024 * 1024:
                logger.warning(f"PDF too large ({content_length / 1e6:.1f}MB): {pdf_url}")
                return None
            pdf_bytes = resp.content
        except requests.RequestException as e:
            logger.error(f"Error downloading PDF {pdf_url}: {e}")
            return None

        try:
            text_parts = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
            full_text = "\n\n".join(text_parts)
            # Clean up
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            full_text = re.sub(r" {2,}", " ", full_text)
            return full_text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_url}: {e}")
            return None

    def fetch_all(self, limit: int = None) -> Iterator[Dict[str, Any]]:
        """Fetch all Eurojust case-law analysis publications with full text."""
        publications = self._get_listing_pages()
        if limit:
            publications = publications[:limit]

        count = 0
        for i, pub in enumerate(publications):
            logger.info(f"[{i+1}/{len(publications)}] Processing: {pub['title'][:70]}...")

            meta = self._get_pdf_url_and_metadata(pub["url"])
            if not meta:
                logger.warning(f"  Could not get metadata for {pub['url']}")
                time.sleep(1.5)
                continue

            if not meta["pdf_url"]:
                logger.warning(f"  No PDF found for {pub['title']}")
                time.sleep(1.5)
                continue

            logger.info(f"  Downloading PDF: {meta['pdf_url']}")
            text = self._extract_text_from_pdf(meta["pdf_url"])
            if not text or len(text) < 200:
                logger.warning(f"  Insufficient text from PDF ({len(text) if text else 0} chars)")
                time.sleep(1.5)
                continue

            # Use date from listing page (most reliable), fall back to meta
            date = pub.get("date") or meta.get("date")

            yield {
                "title": pub["title"],
                "page_url": pub["url"],
                "pdf_url": meta["pdf_url"],
                "date": date,
                "description": meta.get("description", ""),
                "isbn": meta.get("isbn", ""),
                "doi": meta.get("doi", ""),
                "text": text,
            }
            count += 1
            if limit and count >= limit:
                break

            time.sleep(2)

        logger.info(f"Fetched {count} publications with full text")

    def fetch_updates(self, since: datetime) -> Iterator[Dict[str, Any]]:
        """Fetch recent publications only."""
        for doc in self.fetch_all():
            if doc.get("date"):
                try:
                    doc_date = datetime.fromisoformat(doc["date"])
                    if doc_date >= since:
                        yield doc
                except ValueError:
                    yield doc
            else:
                yield doc

    def normalize(self, raw_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw document to the standard schema."""
        # Build a stable ID from the URL slug
        slug = raw_doc["page_url"].rstrip("/").split("/")[-1]
        doc_id = f"eurojust-{slug}"

        date = raw_doc.get("date")
        if date:
            # Normalize to ISO format
            try:
                date = datetime.fromisoformat(date).strftime("%Y-%m-%d")
            except ValueError:
                pass

        return {
            "_id": doc_id,
            "_source": "EU/Eurojust",
            "_type": "doctrine",
            "_fetched_at": datetime.now().isoformat(),
            "title": raw_doc["title"],
            "text": raw_doc["text"],
            "date": date,
            "url": raw_doc["page_url"],
            "pdf_url": raw_doc.get("pdf_url", ""),
            "description": raw_doc.get("description", ""),
            "isbn": raw_doc.get("isbn", ""),
            "doi": raw_doc.get("doi", ""),
            "language": "en",
        }


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("bootstrap", "bootstrap-fast"):
        fetcher = EurojustFetcher()
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        is_sample = "--sample" in sys.argv
        target = 15 if is_sample else None

        logger.info(f"Starting bootstrap ({'sample' if is_sample else 'full'})...")

        count = 0
        for raw_doc in fetcher.fetch_all(limit=target + 5 if target else None):
            if target and count >= target:
                break

            normalized = fetcher.normalize(raw_doc)
            text_len = len(normalized.get("text", ""))
            if text_len < 200:
                continue

            # Use hash suffix to avoid filename collisions from truncation
            id_str = normalized['_id']
            if len(id_str) > 80:
                h = hashlib.md5(id_str.encode()).hexdigest()[:8]
                id_str = f"{id_str[:71]}-{h}"
            filename = f"{id_str}.json"
            filepath = sample_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)

            logger.info(f"  Saved [{count+1}]: {normalized['title'][:60]} ({text_len:,} chars)")
            count += 1

        logger.info(f"Bootstrap complete. Saved {count} documents.")

        # Summary
        files = list(sample_dir.glob("*.json"))
        total_chars = 0
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
                total_chars += len(data.get("text", ""))

        print(f"\n=== SUMMARY ===")
        print(f"Sample files: {len(files)}")
        print(f"Total text chars: {total_chars:,}")
        print(f"Average chars/doc: {total_chars // max(len(files), 1):,}")
    else:
        fetcher = EurojustFetcher()
        print("Testing Eurojust fetcher...")
        for i, raw_doc in enumerate(fetcher.fetch_all(limit=2)):
            normalized = fetcher.normalize(raw_doc)
            print(f"\n--- Document {i+1} ---")
            print(f"ID: {normalized['_id']}")
            print(f"Title: {normalized['title'][:100]}")
            print(f"Date: {normalized['date']}")
            print(f"Text length: {len(normalized.get('text', '')):,}")
            print(f"Text preview: {normalized.get('text', '')[:300]}...")


if __name__ == "__main__":
    main()
