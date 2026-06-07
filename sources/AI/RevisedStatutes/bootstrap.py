#!/usr/bin/env python3
"""
AI/RevisedStatutes -- Revised Statutes and Regulations of Anguilla

Fetches Anguilla legislation from laws.gov.ai, the official law revision portal
maintained by the Regional Law Revision Centre.

Strategy:
  - The site is a Laravel/Livewire SPA. The initial page load embeds a Livewire
    snapshot JSON that contains structured row data (chapter, title, PDF path).
  - Pagination is URL-based: ?revision=2022+Revision&year=2022&page=N
  - PDFs are served from /storage/{path} on laws.gov.ai.
  - We extract text from PDFs using pdfplumber.

Data:
  - 2022 Revised Edition (latest): ~764 acts and regulations
  - Covers all chapters from A through W
  - Includes both Acts (R.S.A.) and Regulations (R.R.A.)

License: Government of Anguilla — All rights reserved (unofficial online edition)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records for validation
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import io
import json
import logging
import re
import time
import html as htmlmod
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

try:
    import pdfplumber
except ImportError:
    raise ImportError("Install pdfplumber: pip install pdfplumber")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AI.RevisedStatutes")

BASE_URL = "https://laws.gov.ai"
STORAGE_PREFIX = f"{BASE_URL}/storage"
REVISION = "2022 Revision"
REVISION_YEAR = 2022
PER_PAGE = 50


class AnguillaScraper(BaseScraper):
    """
    Scraper for AI/RevisedStatutes -- Anguilla Revised Statutes and Regulations.
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html, application/xhtml+xml",
            },
            timeout=60,
        )

    def _get_page_entries(self, page: int = 1) -> Tuple[List[Dict], int]:
        """
        Fetch one page of the law listing from the Livewire-rendered page.

        Returns (entries, total) where entries is a list of dicts with
        chapter_no, regulation_no, title, pdf_path, date.
        """
        url = f"/?revision={REVISION.replace(' ', '+')}&year={REVISION_YEAR}&page={page}"
        resp = self.client.get(url)
        resp.raise_for_status()

        snapshots = re.findall(r'wire:snapshot="([^"]+)"', resp.text)
        if len(snapshots) < 2:
            logger.warning("Could not find Livewire snapshot on page %d", page)
            return [], 0

        decoded = htmlmod.unescape(snapshots[1])
        data = json.loads(decoded)

        total = data["data"].get("total", 0)
        rows_outer = data["data"].get("rows", [])
        if not rows_outer or not isinstance(rows_outer[0], list):
            return [], total

        entries = []
        for row in rows_outer[0]:
            if not isinstance(row, list) or len(row) < 1:
                continue
            item = row[0]
            if not isinstance(item, dict) or "acts_regulations" not in item:
                continue

            title = item["acts_regulations"][0].get("text", "").strip()
            pdf_path = item["acts_regulations"][0].get("url", "").strip()
            chapter = item["chapter_no"][0].get("text", "").strip()
            regulation = item["regulation_no"][0].get("text", "").strip()
            date_str = item["chapter_no"][0].get("date", "") or item["regulation_no"][0].get("date", "")

            # Skip repealed/inoperative entries without PDFs
            if not pdf_path:
                continue
            if "[Repealed]" in title or "[Inoperative]" in title:
                continue

            entries.append({
                "chapter_no": chapter or regulation,
                "regulation_no": regulation,
                "title": title,
                "pdf_path": pdf_path,
                "date_str": date_str.strip(),
            })

        return entries, total

    def _get_all_entries(self) -> List[Dict]:
        """Paginate through all pages to collect all law entries."""
        all_entries = []
        page = 1

        entries, total = self._get_page_entries(page)
        all_entries.extend(entries)
        logger.info("Page %d: %d entries (total: %d)", page, len(entries), total)

        total_pages = (total + PER_PAGE - 1) // PER_PAGE
        for page in range(2, total_pages + 1):
            time.sleep(1)
            entries, _ = self._get_page_entries(page)
            all_entries.extend(entries)
            logger.info("Page %d: %d entries (cumulative: %d)", page, len(entries), len(all_entries))

        logger.info("Collected %d entries with PDFs across %d pages", len(all_entries), total_pages)
        return all_entries

    def _extract_pdf_text(self, pdf_path: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        url = f"{STORAGE_PREFIX}/{pdf_path}"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to download PDF %s: %s", pdf_path, e)
            return None

        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages_text = []
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    pages_text.append(t)
            pdf.close()
            text = "\n\n".join(pages_text)
            return text if text.strip() else None
        except Exception as e:
            logger.warning("Failed to extract text from PDF %s: %s", pdf_path, e)
            return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Convert DD/MM/YYYY to ISO 8601."""
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str, "%d/%m/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Yield all Anguilla legislation records with full text."""
        entries = self._get_all_entries()

        if sample:
            entries = entries[:15]

        for i, entry in enumerate(entries):
            logger.info(
                "[%d/%d] Fetching: %s (%s)",
                i + 1, len(entries), entry["title"], entry["chapter_no"],
            )

            text = self._extract_pdf_text(entry["pdf_path"])
            if not text:
                logger.warning("No text extracted for %s, skipping", entry["title"])
                continue

            yield {
                "chapter_no": entry["chapter_no"],
                "regulation_no": entry.get("regulation_no", ""),
                "title": entry["title"],
                "text": text,
                "date": self._parse_date(entry["date_str"]),
                "pdf_url": f"{STORAGE_PREFIX}/{entry['pdf_path']}",
                "revision": REVISION,
                "revision_year": REVISION_YEAR,
            }

            time.sleep(1)

    def fetch_updates(self, since: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """No incremental updates — re-bootstrap when new revision is published."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw record into standard schema."""
        doc_id = raw["chapter_no"].replace(" ", "")
        is_regulation = bool(raw.get("regulation_no"))

        return {
            "_id": f"AI-RSA-{doc_id}",
            "_source": "AI/RevisedStatutes",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date"),
            "url": raw["pdf_url"],
            "chapter_no": raw["chapter_no"],
            "document_type": "regulation" if is_regulation else "act",
            "revision": raw.get("revision"),
            "revision_year": raw.get("revision_year"),
            "jurisdiction": "AI",
            "jurisdiction_name": "Anguilla",
        }

    # ── CLI ──────────────────────────────────────────────────────────
    def run_bootstrap(self, sample: bool = False):
        sample_dir = self.source_dir / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for raw in self.fetch_all(sample=sample):
            record = self.normalize(raw)
            out_path = sample_dir / f"{record['_id']}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
            logger.info(
                "Saved %s — %s (%d chars)",
                record["_id"], record["title"], len(record["text"]),
            )

        logger.info("Bootstrap complete: %d records saved to %s", count, sample_dir)
        return count

    def run_test(self):
        """Quick connectivity test."""
        entries, total = self._get_page_entries(1)
        logger.info("Test: %d entries on page 1, %d total in dataset", len(entries), total)
        if entries:
            text = self._extract_pdf_text(entries[0]["pdf_path"])
            logger.info(
                "Test PDF: %s — %d chars",
                entries[0]["title"],
                len(text) if text else 0,
            )
        return bool(entries)


if __name__ == "__main__":
    scraper = AnguillaScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|test] [--sample]")
        sys.exit(1)

    cmd = sys.argv[1]
    sample = "--sample" in sys.argv

    if cmd == "bootstrap":
        count = scraper.run_bootstrap(sample=sample)
        print(f"Done: {count} records")
    elif cmd == "test":
        ok = scraper.run_test()
        sys.exit(0 if ok else 1)
    elif cmd == "bootstrap-fast":
        count = scraper.run_bootstrap(sample=sample)
        print(f"Done: {count} records")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
