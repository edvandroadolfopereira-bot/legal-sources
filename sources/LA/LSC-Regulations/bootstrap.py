#!/usr/bin/env python3
"""
LA/LSC-Regulations -- Lao Securities Commission Office (Capital Market Regulations)

Fetches the LSC Office's English-language capital-market legal corpus: the Law on
Securities, regulations, decisions, guidelines/instructions and notifications.
Each document is a PDF hosted under https://lsc.gov.la/Doc_legal/ and linked from
PHP listing tables under https://lsc.gov.la/EN/legislation/. Full text is extracted
with pdfplumber.

Listing tables have the shape:
    <tr><td>{ref no}</td><td>{title}</td><td>{ISO date}</td>
        <td><a href="../../Doc_legal/{file}.pdf">download</a></td></tr>
Rows without a Doc_legal PDF link (commented-out placeholders, href="#") are skipped.

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
logger = logging.getLogger("legal-data-hunter.LA.LSC-Regulations")

BASE = "https://lsc.gov.la/EN/legislation/"

# Listing categories on the LSC site. "proposed_to_lsc" is intentionally excluded:
# it holds third-party vendor submissions (e.g. Thai-language price quotations),
# not LSC legislation.
CATEGORIES = [
    "laws",
    "regulation",
    "decree",
    "guideline",
    "notification",
    "order",
    "ordinance",
    "agreement",
    "regulation_drafting",
    "regulation_plan",
]

MAX_PAGES = 5
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{2}/\d{2}/\d{4}$")


class LSCScraper(BaseScraper):
    """
    Scraper for LA/LSC-Regulations.
    Country: LA
    URL: https://lsc.gov.la/EN/

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (open-data research project)",
        })

    @staticmethod
    def _norm_date(raw: str) -> Optional[str]:
        """Normalize a cell date to ISO 8601 (YYYY-MM-DD)."""
        raw = (raw or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            return raw
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
        if m:
            d, mo, y = m.groups()
            return f"{y}-{mo}-{d}"
        return None

    def _parse_listing(self, category: str, page: int) -> list[dict]:
        """Parse one listing page, returning rows that have a real PDF link."""
        from bs4 import BeautifulSoup

        url = f"{BASE}{category}.php?page={page}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch listing {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        docs = []

        for row in soup.find_all("tr"):
            link = None
            for a in row.find_all("a", href=True):
                if "Doc_legal" in a["href"] and a["href"].lower().endswith(".pdf"):
                    link = a["href"]
                    break
            if not link:
                continue

            pdf_url = urljoin(url, link)
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            text_cells = [c for c in cells if c]

            ref_no = ""
            date = None
            title = ""
            for c in text_cells:
                if not date and DATE_RE.match(c):
                    date = self._norm_date(c)
                elif not title or len(c) > len(title):
                    if not DATE_RE.match(c):
                        title = c if len(c) > len(title) else title
            # ref number is usually the first short non-date, non-title cell
            for c in text_cells:
                if c != title and not DATE_RE.match(c):
                    ref_no = c
                    break

            # Fall back to the PDF filename if no title cell present
            if not title:
                title = re.sub(r"\.pdf$", "", link.rsplit("/", 1)[-1]).replace("%20", " ").strip()

            docs.append({
                "title": title,
                "ref_no": ref_no,
                "date": date,
                "pdf_url": pdf_url,
                "category": category,
            })

        return docs

    def _collect_documents(self) -> list[dict]:
        """Walk every category's listing pages and collect document metadata."""
        all_docs = []
        seen = set()

        for category in CATEGORIES:
            for page in range(1, MAX_PAGES + 1):
                rows = self._parse_listing(category, page)
                if not rows:
                    break
                new = 0
                for doc in rows:
                    if doc["pdf_url"] in seen:
                        continue
                    seen.add(doc["pdf_url"])
                    all_docs.append(doc)
                    new += 1
                time.sleep(1)
                if new == 0:
                    break

        logger.info(f"Collected {len(all_docs)} document links across {len(CATEGORIES)} categories")
        return all_docs

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract its text via pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=120)
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
        return text if len(text) >= 200 else None

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform a raw document into the standard schema."""
        text = (raw.get("text") or "").strip()
        if len(text) < 200:
            return None
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        url_hash = hashlib.md5(raw["pdf_url"].encode("utf-8")).hexdigest()[:12]
        doc_id = f"LA-LSC-{url_hash}"

        return {
            "_id": doc_id,
            "_source": "LA/LSC-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": raw.get("date"),
            "url": raw["pdf_url"],
            "category": raw.get("category", ""),
            "reference_number": raw.get("ref_no", ""),
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Fetch all LSC regulatory documents with full PDF text."""
        documents = self._collect_documents()
        logger.info(f"Processing {len(documents)} documents")

        yielded = 0
        skipped = 0
        for i, doc in enumerate(documents):
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
            time.sleep(1.5)

        logger.info(f"Done. Yielded: {yielded}, Skipped: {skipped}")

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        """No incremental API; re-fetch everything."""
        yield from self.fetch_all()

    def test(self) -> dict:
        """Quick connectivity test."""
        url = f"{BASE}laws.php?page=1"
        resp = self.session.get(url, timeout=30)
        return {
            "status": "ok" if resp.status_code == 200 else "error",
            "http_code": resp.status_code,
            "url": url,
        }


if __name__ == "__main__":
    scraper = LSCScraper()

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
        limit = 20 if sample_mode else 99999
        for record in gen:
            count += 1
            if sample_mode:
                outpath = sample_dir / f"{count:04d}.json"
                outpath.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                print(f"[{count}] {record['title'][:60]} ({len(record['text'])} chars)")
            else:
                print(json.dumps(record, ensure_ascii=False))
            if count >= limit:
                break
        print(f"\nTotal records: {count}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
