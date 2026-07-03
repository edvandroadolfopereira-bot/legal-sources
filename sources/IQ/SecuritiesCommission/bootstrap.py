#!/usr/bin/env python3
"""
IQ/SecuritiesCommission — Iraqi Securities Commission Regulations & Decisions

Fetches regulations, instructions, related laws, and board decisions from the ISC.

Strategy:
  1. Scrape legislation category pages (pages/42-45) for document links
  2. For PDFs: download and extract text with pdfplumber
  3. For board decisions: fetch HTML detail pages and extract text content

Usage:
  python bootstrap.py bootstrap           # Full initial pull
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py test-api            # Quick connectivity test
"""

import io
import re
import sys
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.IQ.SecuritiesCommission")

BASE_URL = "https://www.isc.gov.iq"
SOURCE_ID = "IQ/SecuritiesCommission"

MIN_TEXT_LENGTH = 200

CATEGORY_PAGES = {
    "commission_law": {"path": "/en/pages/42", "doc_type": "legislation", "category": "Commission Law"},
    "related_laws": {"path": "/en/pages/43", "doc_type": "legislation", "category": "Related Laws"},
    # Arabic pages have far more PDF links (66 vs 3 on English)
    "instructions_regulations": {"path": "/pages/44", "doc_type": "legislation", "category": "Instructions and Regulations"},
    "board_decisions": {"path": "/en/pages/45", "doc_type": "legislation", "category": "Board Decisions"},
}


class ISCScraper(BaseScraper):

    def __init__(self):
        super().__init__(str(Path(__file__).parent))
        self.http = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (open legal data research)",
                "Accept": "text/html, application/xhtml+xml, */*",
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            },
        )

    # ── PDF text extraction ────────────────────────────────────────────

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract text with pdfplumber."""
        try:
            import pdfplumber
            resp = self.http.get(pdf_url, timeout=120)
            if resp.status_code != 200:
                logger.warning("PDF download failed (%d): %s", resp.status_code, pdf_url)
                return None
            if not resp.content[:5] == b"%PDF-":
                logger.warning("Not a PDF: %s", pdf_url)
                return None
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                text = "\n\n".join(pages)
                if len(text.strip()) >= MIN_TEXT_LENGTH:
                    return text.strip()
                logger.warning("PDF text too short (%d chars): %s", len(text.strip()), pdf_url)
        except Exception as e:
            logger.warning("pdfplumber failed for %s: %s", pdf_url, e)
        return None

    # ── HTML text extraction ───────────────────────────────────────────

    def _extract_page_text_from_html(self, html: str) -> Optional[str]:
        """Extract text content from already-fetched HTML."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Remove nav, header, footer, scripts
            for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
                tag.decompose()
            # ISC uses Tailwind CSS — find the content div by looking for
            # the div with class containing 'pb-25' or 'text-sm' which wraps decision text
            content = soup.find("div", class_=lambda c: c and "pb-25" in c)
            if not content:
                content = soup.find("div", class_=re.compile(r"(content|page-body|article|main)", re.I))
            if not content:
                content = soup.find("main") or soup.find("article")
            if not content:
                # Fallback: get body text minus navigation noise
                content = soup.body
            if not content:
                return None
            text = content.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace and navigation noise
            text = re.sub(r"\n{3,}", "\n\n", text)
            # Remove common nav prefixes that leak in
            text = re.sub(r"^Home\n.*?\n", "", text, count=1)
            if len(text.strip()) >= 100:
                return text.strip()
            logger.warning("Page text too short (%d chars)", len(text.strip()))
        except Exception as e:
            logger.warning("Page extraction failed: %s", e)
        return None

    # ── Parse category pages ───────────────────────────────────────────

    def _parse_pdf_links(self, html: str) -> list[dict]:
        """Extract PDF links from a category page."""
        soup = BeautifulSoup(html, "html.parser")
        items = []
        seen = set()
        for a in soup.find_all("a", href=lambda h: h and ".pdf" in h.lower()):
            href = a.get("href", "")
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                # Try parent element for title
                parent = a.parent
                if parent:
                    parent_text = parent.get_text(strip=True)
                    if len(parent_text) > len(title or ""):
                        title = parent_text
            if not title or len(title) < 5:
                title = href.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")
            items.append({"title": title, "url": full_url})
        return items

    def _parse_decision_links(self, html: str) -> list[dict]:
        """Extract board decision page links from the decisions listing."""
        soup = BeautifulSoup(html, "html.parser")
        items = []
        seen = set()
        for a in soup.find_all("a", href=lambda h: h and "/pages/" in h):
            href = a.get("href", "")
            if not href:
                continue
            # Extract page number — only accept IDs >= 200 (skip nav pages < 100)
            page_match = re.search(r"/pages/(\d+)", href)
            if not page_match:
                continue
            page_id = int(page_match.group(1))
            if page_id < 200:
                continue
            full_url = urljoin(BASE_URL, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            date = self._extract_date_from_title(title)
            items.append({"title": title, "url": full_url, "date": date})
        return items

    def _extract_date_from_title(self, title: str) -> Optional[str]:
        """Try to extract a date from a decision title."""
        # Pattern: DD/MM/YYYY
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", title)
        if m:
            day, month, year = m.groups()
            try:
                return f"{year}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                pass
        return None

    # ── Fetch methods ──────────────────────────────────────────────────

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch all ISC documents."""
        record_count = 0
        sample_limit = 15 if sample else 9999

        for cat_key, cat_info in CATEGORY_PAGES.items():
            if record_count >= sample_limit:
                break

            logger.info("Fetching category: %s (%s)", cat_info["category"], cat_info["path"])
            time.sleep(2)
            resp = self.http.get(cat_info["path"], timeout=60)
            if resp.status_code != 200:
                logger.error("Failed to fetch %s: %d", cat_info["path"], resp.status_code)
                continue

            if cat_key == "board_decisions":
                # Board decisions: detail pages with PDF links + HTML summary
                decisions = self._parse_decision_links(resp.text)
                logger.info("Found %d board decisions", len(decisions))
                for decision in decisions:
                    if record_count >= sample_limit:
                        break
                    time.sleep(2)
                    # Fetch detail page
                    detail_resp = self.http.get(decision["url"], timeout=60)
                    if detail_resp.status_code != 200:
                        logger.warning("Failed to fetch decision page: %s", decision["url"])
                        continue
                    # Try PDF extraction first (detail pages often link to PDFs)
                    detail_pdfs = self._parse_pdf_links(detail_resp.text)
                    text = None
                    pdf_url = None
                    for pdf_item in detail_pdfs:
                        time.sleep(1)
                        text = self._extract_pdf_text(pdf_item["url"])
                        if text:
                            pdf_url = pdf_item["url"]
                            break
                    # Fallback to HTML text if no PDF or PDF extraction failed
                    if not text:
                        text = self._extract_page_text_from_html(detail_resp.text)
                    if not text or len(text) < 100:
                        logger.warning("No text for decision: %s", decision["title"])
                        continue
                    record_count += 1
                    yield self.normalize({
                        "title": decision["title"],
                        "text": text,
                        "url": pdf_url or decision["url"],
                        "date": decision.get("date"),
                        "document_type": cat_info["doc_type"],
                        "category": cat_info["category"],
                    })
            else:
                # Laws and regulations are PDFs
                pdfs = self._parse_pdf_links(resp.text)
                logger.info("Found %d PDFs in %s", len(pdfs), cat_info["category"])
                for pdf_item in pdfs:
                    if record_count >= sample_limit:
                        break
                    time.sleep(2)
                    text = self._extract_pdf_text(pdf_item["url"])
                    if not text:
                        logger.warning("No text for PDF: %s", pdf_item["title"])
                        continue
                    record_count += 1
                    yield self.normalize({
                        "title": pdf_item["title"],
                        "text": text,
                        "url": pdf_item["url"],
                        "date": None,
                        "document_type": cat_info["doc_type"],
                        "category": cat_info["category"],
                    })

        logger.info("Total records fetched: %d", record_count)

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Fetch documents updated since a date."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Normalize a raw record into standard schema."""
        title = raw.get("title", "").strip()
        # Clean up titles that are raw PDF filenames
        title = re.sub(r"\s*\[\d+\]\.pdf$", "", title, flags=re.I)
        title = re.sub(r"\.pdf$", "", title, flags=re.I)
        text = raw.get("text", "").strip()
        url = raw.get("url", "")

        # Generate stable ID from URL
        doc_id = re.sub(r"[^a-zA-Z0-9]", "_", url.split("isc.gov.iq")[-1])[:120]

        return {
            "_id": f"IQ_ISC_{doc_id}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": url,
            "document_type": raw.get("document_type", "legislation"),
            "category": raw.get("category", ""),
            "language": "ar" if any("\u0600" <= c <= "\u06FF" for c in title[:20]) else "en",
        }

    # ── CLI ────────────────────────────────────────────────────────────

    def test_api(self):
        """Quick connectivity test."""
        resp = self.http.get("/en/pages/42", timeout=30)
        logger.info("Commission Law page: %d (%d bytes)", resp.status_code, len(resp.text))
        resp2 = self.http.get("/en/pages/45", timeout=30)
        logger.info("Board Decisions page: %d (%d bytes)", resp2.status_code, len(resp2.text))
        return resp.status_code == 200


if __name__ == "__main__":
    scraper = ISCScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap --sample|test-api]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test-api":
        ok = scraper.test_api()
        sys.exit(0 if ok else 1)

    elif cmd == "bootstrap":
        sample = "--sample" in sys.argv
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            outfile = sample_dir / f"{count:04d}.json"
            outfile.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[%d] %s — %d chars", count, record["title"][:60], len(record.get("text", "")))

        logger.info("Done: %d records saved to %s", count, sample_dir)
        if count == 0:
            logger.error("No records fetched — source may be blocked or down")
            sys.exit(1)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
