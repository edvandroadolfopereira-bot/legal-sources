#!/usr/bin/env python3
"""
LK/PUCSL-Regulations -- Public Utilities Commission of Sri Lanka

Fetches the PUCSL legal-document corpus governing Sri Lanka's electricity sector:
acts, regulations, codes, rules, tariff decisions & orders, guidelines, manuals,
methodologies, policies and gazettes. Documents are PDFs hosted in the site's
WordPress media library (wp-content/uploads); full text is extracted via pdfplumber.

The custom `legal_documents` post type is NOT exposed in the WP REST API, so the
scraper reads the HTML archive pages under /legal_documents_types/{category}/.
Each document card has the shape:
    <div class="report-box">
       <div class="header-sm">{title}</div>
       <div class="year">{year}</div>
       <a href="...wp-content/uploads/.../{file}.pdf"> ... </a>
    </div>

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # Sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Re-fetch (no incremental API)
  python bootstrap.py test               # Connectivity test
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
logger = logging.getLogger("legal-data-hunter.LK.PUCSL-Regulations")

BASE = "https://www.pucsl.gov.lk/legal_documents_types/"

# Legal-document taxonomy categories published by PUCSL.
CATEGORIES = [
    "acts",
    "regulations",
    "rules",
    "codes",
    "decisions_orders",
    "bst-and-unt",          # Bulk Supply / Transmission tariff decisions
    "methodologies",
    "guidelines",
    "policies",
    "manuals",
    "gazetts",
]


class PUCSLScraper(BaseScraper):
    """
    Scraper for LK/PUCSL-Regulations.
    Country: LK
    URL: https://www.pucsl.gov.lk/legal_documents_types/regulations/

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0; open-data research)",
        })

    def _parse_category(self, category: str) -> list[dict]:
        """Parse one category archive page into document records."""
        from bs4 import BeautifulSoup

        url = f"{BASE}{category}/"
        try:
            resp = self.session.get(url, timeout=40)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch category {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        docs = []

        for box in soup.select("div.report-box"):
            anchor = None
            for a in box.find_all("a", href=True):
                if a["href"].lower().endswith(".pdf"):
                    anchor = a
                    break
            if not anchor:
                continue

            pdf_url = urljoin(url, anchor["href"])

            title_el = box.select_one(".header-sm")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title:
                title = re.sub(r"\.pdf$", "", pdf_url.rsplit("/", 1)[-1], flags=re.I)
                title = re.sub(r"[-_]+", " ", title).strip()

            year_el = box.select_one(".year")
            year = year_el.get_text(strip=True) if year_el else ""
            year = year if re.match(r"^(19|20)\d{2}$", year) else None

            docs.append({
                "title": title,
                "date": year,            # year-only ISO 8601 representation
                "pdf_url": pdf_url,
                "category": category,
            })

        return docs

    def _collect_documents(self) -> list[dict]:
        """Collect document metadata across all categories, deduped by PDF URL."""
        all_docs = []
        seen = set()
        for category in CATEGORIES:
            rows = self._parse_category(category)
            for doc in rows:
                if doc["pdf_url"] in seen:
                    continue
                seen.add(doc["pdf_url"])
                all_docs.append(doc)
            logger.info(f"{category}: {len(rows)} cards ({len(all_docs)} unique so far)")
            time.sleep(1)
        logger.info(f"Collected {len(all_docs)} unique documents")
        return all_docs

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract its text via pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=150)
        except Exception as e:
            logger.warning(f"Failed to download {pdf_url}: {e}")
            return None

        ctype = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "pdf" not in ctype.lower() or len(resp.content) < 1000:
            logger.warning(f"Not a PDF ({resp.status_code}, {ctype}): {pdf_url}")
            return None

        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages = [p.extract_text() or "" for p in pdf.pages]
            pdf.close()
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return None

        text = "\n\n".join(p for p in pages if p.strip())
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text if len(text) >= 300 else None

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform a raw document into the standard schema."""
        text = (raw.get("text") or "").strip()
        if len(text) < 300:
            return None
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        url_hash = hashlib.md5(raw["pdf_url"].encode("utf-8")).hexdigest()[:12]
        doc_id = f"LK-PUCSL-{url_hash}"

        return {
            "_id": doc_id,
            "_source": "LK/PUCSL-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": raw["pdf_url"],
            "category": raw.get("category", ""),
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Fetch all PUCSL legal documents with full PDF text."""
        documents = self._collect_documents()
        logger.info(f"Processing {len(documents)} documents")

        yielded = 0
        skipped = 0
        for i, doc in enumerate(documents):
            if (i + 1) % 15 == 0:
                logger.info(f"[{i+1}/{len(documents)}] yielded={yielded} skipped={skipped}")
            text = self._extract_pdf_text(doc["pdf_url"])
            if not text:
                skipped += 1
                continue
            doc["text"] = text
            normalized = self.normalize(doc)
            if normalized:
                yielded += 1
                yield normalized
            else:
                skipped += 1
            time.sleep(1.2)

        logger.info(f"Done. Yielded: {yielded}, Skipped: {skipped}")

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """No incremental API; re-fetch everything."""
        yield from self.fetch_all()

    def test(self) -> dict:
        """Quick connectivity test."""
        url = f"{BASE}regulations/"
        resp = self.session.get(url, timeout=30)
        return {
            "status": "ok" if resp.status_code == 200 else "error",
            "http_code": resp.status_code,
            "url": url,
        }


if __name__ == "__main__":
    scraper = PUCSLScraper()

    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test":
        print(json.dumps(scraper.test(), indent=2))
    elif command in ("bootstrap", "bootstrap-fast", "update"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        gen = scraper.fetch_all() if command != "update" else scraper.fetch_updates()
        count = 0
        limit = 15 if sample_mode else 99999
        for record in gen:
            count += 1
            if sample_mode:
                outpath = sample_dir / f"{count:04d}.json"
                outpath.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                print(f"[{count}] {record['title'][:55]} ({len(record['text'])} chars)")
            else:
                print(json.dumps(record, ensure_ascii=False))
            if count >= limit:
                break
        print(f"\nTotal records: {count}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
