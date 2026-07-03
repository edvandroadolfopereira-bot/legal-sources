#!/usr/bin/env python3
"""
CU/GacetaLegislaciones -- Cuba Consolidated Key Laws (Gaceta Oficial)

Fetches curated consolidated Cuban laws from the Gaceta Oficial's
"Algunas Legislaciones Cubanas" section.

Strategy:
  - Paginate the curated laws listing at /es/algunas-legislaciones-cubanas?page=N
  - Extract PDF download URLs from each page
  - Download PDFs and extract full text with pdfplumber
  - ~55 curated laws: Constitution, Penal Code, Family Code, Labor Code, etc.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.CU.GacetaLegislaciones")

BASE_URL = "https://www.gacetaoficial.gob.cu"
LISTING_URL = BASE_URL + "/es/algunas-legislaciones-cubanas"
CRAWL_DELAY = 2


class CubaGacetaLegislacionesScraper(BaseScraper):
    """
    Scraper for CU/GacetaLegislaciones -- Cuba Consolidated Key Laws.
    Country: CU
    URL: https://www.gacetaoficial.gob.cu/es/algunas-legislaciones-cubanas

    Data types: legislation
    Auth: none (Open Data)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-CU,es;q=0.9,en;q=0.5",
                "Referer": LISTING_URL,
            },
            timeout=60,
        )

    def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch an HTML page with crawl delay."""
        try:
            time.sleep(CRAWL_DELAY)
            resp = self.client.session.get(url, timeout=60)
            if resp.status_code == 403:
                logger.warning(f"403 Forbidden: {url}")
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _fetch_pdf_bytes(self, url: str) -> Optional[bytes]:
        """Download a PDF file."""
        try:
            time.sleep(CRAWL_DELAY)
            resp = self.client.session.get(url, timeout=120)
            resp.raise_for_status()
            if len(resp.content) < 500:
                logger.warning(f"PDF too small ({len(resp.content)} bytes): {url}")
                return None
            return resp.content
        except Exception as e:
            logger.warning(f"Failed to download PDF {url}: {e}")
            return None

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF using pdfplumber."""
        try:
            import pdfplumber
            import io
            pages_text = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
            return "\n\n".join(pages_text)
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}, trying pypdf")
            try:
                from pypdf import PdfReader
                import io
                reader = PdfReader(io.BytesIO(pdf_bytes))
                pages_text = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                return "\n\n".join(pages_text)
            except Exception as e2:
                logger.error(f"All PDF extractors failed: {e2}")
                return ""

    def _parse_listing_page(self, html: str) -> list:
        """Parse a listing page, returning list of (title, pdf_url) tuples."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        items = []

        # Structure: table rows with title in views-field-title td,
        # PDF link in views-field-field-fichero-legislacion-cubana td
        for row in soup.find_all("tr"):
            title_td = row.find("td", class_="views-field-title")
            link_td = row.find("td", class_="views-field-field-fichero-legislacion-cubana")
            if not title_td or not link_td:
                continue
            a_tag = link_td.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"]
            if not href.lower().endswith(".pdf"):
                continue

            title_text = title_td.get_text(strip=True).rstrip(".")

            if href.startswith("http"):
                pdf_url = href
            elif href.startswith("/"):
                pdf_url = BASE_URL + href
            else:
                pdf_url = BASE_URL + "/" + href

            items.append((title_text, pdf_url))

        return items

    def _has_next_page(self, html: str, current_page: int) -> bool:
        """Check if there's a next page in pagination."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        next_page = current_page + 1
        for link in soup.find_all("a", href=True):
            if f"page={next_page}" in link["href"]:
                return True
        return False

    def _parse_law_metadata(self, title: str) -> Dict[str, Any]:
        """Extract law number, type, and date from title string."""
        meta = {"law_number": None, "law_type": None, "date": None}

        # Match patterns like "Ley No. 151", "Decreto-Ley 86/2024", etc.
        num_match = re.search(
            r'(?:Ley|Decreto[- ]?Ley|Decreto)\s*(?:No\.?\s*)?(\d+(?:/\d+)?)',
            title, re.IGNORECASE
        )
        if num_match:
            meta["law_number"] = num_match.group(1)

        # Law type
        if re.search(r'Decreto[- ]?Ley', title, re.IGNORECASE):
            meta["law_type"] = "decreto-ley"
        elif re.search(r'Decreto\b', title, re.IGNORECASE):
            meta["law_type"] = "decreto"
        elif re.search(r'Ley\b', title, re.IGNORECASE):
            meta["law_type"] = "ley"
        elif re.search(r'C[oó]digo', title, re.IGNORECASE):
            meta["law_type"] = "codigo"
        elif re.search(r'Constituci[oó]n', title, re.IGNORECASE):
            meta["law_type"] = "constitucion"

        # Date patterns
        date_match = re.search(
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', title
        )
        if date_match:
            months = {
                "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
            }
            day, month_name, year = date_match.groups()
            month = months.get(month_name.lower(), "01")
            meta["date"] = f"{year}-{month}-{day.zfill(2)}"
        else:
            year_match = re.search(r'/(\d{4})\b', title)
            if year_match:
                meta["date"] = f"{year_match.group(1)}-01-01"
            else:
                year_match2 = re.search(r'\b(19\d{2}|20\d{2})\b', title)
                if year_match2:
                    meta["date"] = f"{year_match2.group(1)}-01-01"

        return meta

    def _make_id(self, pdf_url: str) -> str:
        """Create a stable ID from the PDF URL."""
        filename = pdf_url.split("/")[-1]
        filename = re.sub(r'\.(pdf|PDF)$', '', filename)
        return filename

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all curated Cuban laws."""
        seen_urls = set()
        page = 0

        while True:
            url = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
            logger.info(f"Fetching listing page {page}: {url}")
            html = self._fetch_html(url)
            if not html:
                logger.warning(f"Failed to fetch page {page}, stopping")
                break

            items = self._parse_listing_page(html)
            if not items:
                logger.info(f"No items on page {page}, stopping")
                break

            new_items = 0
            for title, pdf_url in items:
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)
                new_items += 1

                record = self._process_law(title, pdf_url)
                if record:
                    yield record

            logger.info(f"Page {page}: {new_items} new items")

            if not self._has_next_page(html, page):
                break
            page += 1

    def _process_law(self, title: str, pdf_url: str) -> Optional[Dict[str, Any]]:
        """Download and process a single law PDF."""
        logger.info(f"Processing: {title[:80]}...")

        pdf_bytes = self._fetch_pdf_bytes(pdf_url)
        if not pdf_bytes:
            logger.warning(f"Could not download PDF: {pdf_url}")
            return None

        text = self._extract_pdf_text(pdf_bytes)
        if not text or len(text) < 100:
            logger.warning(f"No text extracted from {pdf_url} ({len(text) if text else 0} chars)")
            return None

        meta = self._parse_law_metadata(title)
        doc_id = self._make_id(pdf_url)

        return {
            "_id": doc_id,
            "_source": "CU/GacetaLegislaciones",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title.strip(),
            "text": text,
            "date": meta["date"],
            "url": pdf_url,
            "law_number": meta["law_number"],
            "law_type": meta["law_type"],
            "language": "es",
            "jurisdiction": "CU",
        }

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch all — this is a small curated list, always re-fetch."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Records are already normalized during fetch."""
        return raw


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CU/GacetaLegislaciones scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch only 15 sample records")
    parser.add_argument("--full", action="store_true",
                        help="Fetch all records")
    args = parser.parse_args()

    scraper = CubaGacetaLegislacionesScraper()

    if args.command == "test":
        html = scraper._fetch_html(LISTING_URL)
        if html:
            items = scraper._parse_listing_page(html)
            print(f"OK: Found {len(items)} items on first page")
        else:
            print("FAIL: Could not fetch listing page")
            sys.exit(1)
        return

    sample_mode = args.sample or args.command == "bootstrap-fast"
    max_records = 15 if sample_mode else 9999

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    jsonl_path = data_dir / "records.jsonl"

    count = 0
    with open(jsonl_path, "w", encoding="utf-8") as jsonl_f:
        for record in scraper.fetch_all():
            count += 1
            jsonl_f.write(json.dumps(record, ensure_ascii=False) + "\n")

            if count <= 15:
                sample_path = sample_dir / f"{record['_id'][:80]}.json"
                with open(sample_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)

            logger.info(
                f"[{count}] {record['title'][:60]} — "
                f"{len(record.get('text', ''))} chars"
            )

            if count >= max_records:
                logger.info(f"Reached limit of {max_records} records")
                break

    print(f"\nDone: {count} records saved to {jsonl_path}")
    print(f"Samples: {min(count, 15)} files in {sample_dir}/")


if __name__ == "__main__":
    main()
