#!/usr/bin/env python3
"""
BH/MOLA-Laws -- Bahrain Ministry of Legal Affairs: Consolidated Laws

Fetches consolidated laws and legislative decrees published in English/Arabic
by the Kingdom of Bahrain's Ministry of Legal Affairs (MoLA).

Strategy:
  - Fetch the listing page https://www.mola.gov.bh/Legislation/Laws/
  - Parse the structured table rows (data-title / data-year / data-lawno /
    data-type / data-translation + the PDF link)
  - Download each law PDF and extract text with PyMuPDF (fitz)
  - Each PDF is a bilingual (English + Arabic) consolidated law text,
    with subsequent amendments noted inline.

Data: ~58 consolidated laws & legislative decrees (bilingual, full text).
License: Bahrain Government Open Data (commercial use OK with attribution).
Rate limit: 0.5 req/sec.

Usage:
  python bootstrap.py bootstrap            # Full pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for full pull (VPS wrapper)
  python bootstrap.py test-api             # Connectivity test
"""

import sys
import json
import logging
import re
import time
from html import unescape
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip3 install PyMuPDF")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BH.MOLA-Laws")

BASE_URL = "https://www.mola.gov.bh"
LISTING_URL = f"{BASE_URL}/Legislation/Laws/"


def clean_text(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks."""
    if not text:
        return ""
    # Normalise line endings and strip per-line whitespace
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]
    out = []
    blank = 0
    for ln in lines:
        if ln:
            out.append(ln)
            blank = 0
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


class BHMOLALawsScraper(BaseScraper):
    """Scraper for BH/MOLA-Laws -- Bahrain consolidated laws."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en,ar;q=0.8",
        })

    def _fetch_listing(self) -> str:
        """Download the laws listing HTML."""
        for attempt in range(3):
            try:
                self.rate_limiter.wait()
                resp = self.session.get(LISTING_URL, timeout=60)
                if resp.status_code == 200 and len(resp.text) > 1000:
                    return resp.text
                logger.warning(f"Listing: HTTP {resp.status_code}")
            except requests.RequestException as e:
                logger.warning(f"Listing attempt {attempt+1}: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("Could not fetch MoLA laws listing")

    def _parse_listing(self, html: str) -> list:
        """Parse table rows into law metadata dicts."""
        rows = re.findall(r'<tr class="table-body-row"(.*?)</tr>', html, re.S)
        laws = []
        for r in rows:
            pdf = re.search(r'href="([^"]+\.pdf)"', r)
            if not pdf:
                continue
            href = pdf.group(1)
            url = href if href.startswith("http") else BASE_URL + href

            def attr(name):
                m = re.search(rf'data-{name}="([^"]*)"', r)
                return unescape(m.group(1)).strip() if m else ""

            en_title = re.search(r'class="law-title">([^<]+)<', r)
            title = unescape(en_title.group(1)).strip() if en_title else attr("title")
            laws.append({
                "law_no": attr("lawno"),
                "year": attr("year"),
                "type": attr("type"),
                "translation": attr("translation"),
                "title": title,
                "url": url,
                "pdf_path": href,
            })
        # De-duplicate by URL, preserving order
        seen = set()
        uniq = []
        for law in laws:
            if law["url"] in seen:
                continue
            seen.add(law["url"])
            uniq.append(law)
        return uniq

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download a law PDF with retries."""
        for attempt in range(3):
            try:
                self.rate_limiter.wait()
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content
                if resp.status_code == 404:
                    return None
                logger.warning(f"{url}: HTTP {resp.status_code}")
            except requests.RequestException as e:
                logger.warning(f"{url} attempt {attempt+1}: {e}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        return None

    def _extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using PyMuPDF."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text and text.strip():
                pages.append(text.strip())
        doc.close()
        return clean_text("\n\n".join(pages))

    def _iter_laws(self) -> Generator[dict, None, None]:
        html = self._fetch_listing()
        laws = self._parse_listing(html)
        logger.info(f"Found {len(laws)} laws on MoLA listing")
        for law in laws:
            pdf_bytes = self._download_pdf(law["url"])
            if pdf_bytes is None:
                logger.warning(f"Law {law['law_no']}/{law['year']}: PDF unavailable")
                continue
            text = self._extract_text(pdf_bytes)
            if not text or len(text) < 100:
                logger.warning(
                    f"Law {law['law_no']}/{law['year']}: insufficient text "
                    f"({len(text)} chars)"
                )
                continue
            yield {**law, "text": text, "pdf_size": len(pdf_bytes)}

    def fetch_all(self) -> Generator[dict, None, None]:
        yield from self._iter_laws()

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        # Listing is small; re-scan everything (upsert dedups downstream).
        yield from self._iter_laws()

    def normalize(self, raw: dict) -> dict:
        law_no = raw.get("law_no") or "NA"
        year = raw.get("year") or "NA"
        slug = Path(raw["pdf_path"]).stem
        return {
            "_id": f"BH-MOLA-{slug}",
            "_source": "BH/MOLA-Laws",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title") or f"Bahrain Law No. ({law_no}) of {year}",
            "text": raw["text"],
            "date": f"{year}-01-01" if year.isdigit() else None,
            "url": raw["url"],
            "law_number": law_no,
            "year": year,
            "instrument_type": raw.get("type"),
            "language": "ar+en" if "en" in (raw.get("translation") or "") else "ar",
            "pdf_size_bytes": raw.get("pdf_size"),
        }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="BH/MOLA-Laws bootstrap")
    parser.add_argument(
        "command", choices=["bootstrap", "bootstrap-fast", "test-api"]
    )
    parser.add_argument("--sample", action="store_true", help="Fetch 15 sample records only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = BHMOLALawsScraper()

    if args.command == "test-api":
        logger.info("Testing connectivity...")
        html = scraper._fetch_listing()
        laws = scraper._parse_listing(html)
        logger.info(f"Listing OK — {len(laws)} laws found")
        if not laws:
            logger.error("API FAILED — no laws parsed")
            sys.exit(1)
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    limit = 15 if args.sample else 999999

    for raw in scraper.fetch_all():
        if count >= limit:
            break
        record = scraper.normalize(raw)
        out_path = sample_dir / f"{record['_id']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        count += 1
        logger.info(
            f"[{count}] {record['_id']}: {len(record['text'])} chars, "
            f"{record['title'][:60]}"
        )

    logger.info(f"Done. {count} laws saved to {sample_dir}")


if __name__ == "__main__":
    main()
