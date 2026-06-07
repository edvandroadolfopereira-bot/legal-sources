#!/usr/bin/env python3
"""
NA/NAMFISA-Instruments — NAMFISA regulatory instruments (Acts, regulations,
standards, directives, circulars)

NAMFISA (https://www.namfisa.com.na) publishes regulatory instruments across
multiple industry pages using the WordPress Download Manager plugin. Each
document is a PDF (typically a Government Gazette notice).

Strategy:
  1. Crawl industry pages and the regulatory-frameworks page for download links
     (data-downloadurl attributes from wpDownloadManager tables).
  2. Deduplicate by WordPress Download Manager ID (wpdmdl parameter).
  3. Download each PDF and extract full text with pdfplumber.
  4. Drop image-only scans with a text quality filter.

Content is in English. Free access, no authentication.

Usage:
  python bootstrap.py bootstrap --sample   # sample records
  python bootstrap.py bootstrap            # full pull
  python bootstrap.py bootstrap --full     # alias for full pull
  python bootstrap.py bootstrap-fast       # alias for bootstrap
  python bootstrap.py update               # incremental (re-crawl)
  python bootstrap.py test-api             # connectivity check
"""

import io
import re
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from html import unescape
from typing import Generator, Optional
from urllib.parse import urljoin, parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NA.NAMFISA-Instruments")

BASE_URL = "https://www.namfisa.com.na"
SOURCE_ID = "NA/NAMFISA-Instruments"

# Pages to crawl for documents. Each tuple: (path, category).
PAGES = [
    ("/regulatory-frameworks/", "regulatory-frameworks"),
    ("/short-term-insurance/", "short-term-insurance"),
    ("/long-term-insurance/", "long-term-insurance"),
    ("/pension-funds/", "pension-funds"),
    ("/medical-aid-funds/", "medical-aid-funds"),
    ("/capital-markets/", "capital-markets"),
    ("/microlending/", "microlending"),
    ("/friendly-societies/", "friendly-societies"),
]

MAX_PDF_BYTES = 30_000_000
MAX_PDF_PAGES = 120
MIN_TEXT_CHARS = 300

MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_clean(text: str) -> bool:
    """Reject image-only scans: real text has many long word tokens."""
    if len(text) < MIN_TEXT_CHARS:
        return False
    tokens = [t for t in text.split() if any(ch.isalpha() for ch in t)]
    if len(tokens) < 50:
        return False
    long_tokens = [t for t in tokens if len(t) >= 4]
    return (len(long_tokens) / len(tokens)) >= 0.30


def _parse_date(text: str, update_date: Optional[str] = None) -> Optional[str]:
    """Best-effort ISO date from PDF header or table update date."""
    head = text[:1500]
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", head)
    if m:
        d = int(m.group(1))
        mo = MONTHS.get(m.group(2).lower())
        y = int(m.group(3))
        if mo and 1900 < y < 2100:
            try:
                return datetime(y, mo, d).date().isoformat()
            except ValueError:
                pass
    m = re.search(r"\b(19|20)\d{2}\b", head)
    if m:
        return f"{m.group(0)}-01-01"
    if update_date:
        m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", update_date)
        if m:
            mo = MONTHS.get(m.group(1).lower())
            d = int(m.group(2))
            y = int(m.group(3))
            if mo and 1900 < y < 2100:
                try:
                    return datetime(y, mo, d).date().isoformat()
                except ValueError:
                    pass
    return None


def _get_wpdmdl(url: str) -> Optional[str]:
    """Extract WordPress Download Manager ID from URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    ids = qs.get("wpdmdl", [])
    return ids[0] if ids else None


def _classify_doc_type(title: str) -> str:
    """Classify document based on title keywords."""
    t = title.lower()
    if "act " in t or "act," in t or t.startswith("act"):
        return "act"
    if "regulation" in t:
        return "regulation"
    if "standard" in t:
        return "standard"
    if "circular" in t:
        return "circular"
    if "directive" in t:
        return "directive"
    if "guideline" in t:
        return "guideline"
    if "determination" in t:
        return "determination"
    if "notice" in t or "gazette" in t or "gov-n" in t.replace(" ", ""):
        return "notice"
    if "bill" in t:
        return "bill"
    if "draft" in t:
        return "draft"
    return "instrument"


class NAMFISAInstrumentsScraper(BaseScraper):

    def __init__(self):
        super().__init__(str(Path(__file__).parent))
        self.http = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/pdf,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=90,
            respect_robots=False,
        )

    def _get_html(self, path: str) -> Optional[str]:
        url = urljoin(BASE_URL, path)
        try:
            resp = self.http.get(url, timeout=60)
        except Exception as e:
            logger.warning("Page fetch error %s: %s", path, e)
            return None
        if resp.status_code != 200:
            logger.warning("Page %s returned HTTP %d", path, resp.status_code)
            return None
        return resp.text

    def _crawl_documents(self) -> list[dict]:
        """Crawl all industry pages for download links. Deduplicate by wpdmdl."""
        docs: dict[str, dict] = {}

        for page_path, category in PAGES:
            html = self._get_html(page_path)
            if not html:
                continue

            # Parse table rows: each has title (<strong>), update date, and
            # download link (data-downloadurl attribute).
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
            for row in rows:
                # Skip header rows
                if "<th" in row:
                    continue

                # Extract title
                title_m = re.search(r"<strong>([^<]+)</strong>", row)
                if not title_m:
                    continue
                title = unescape(title_m.group(1)).strip()

                # Extract update date
                date_m = re.search(
                    r"<span[^>]*class=['\"]__dt_update_date[^'\"]*['\"][^>]*>"
                    r"([^<]+)</span>", row)
                update_date = date_m.group(1).strip() if date_m else None

                # Extract download URL
                dl_m = re.search(r'data-downloadurl="([^"]+)"', row)
                if not dl_m:
                    continue
                download_url = dl_m.group(1)

                # Remove refresh parameter (session-specific)
                clean_url = re.sub(r"&refresh=[a-f0-9]+", "", download_url)

                wpdmdl = _get_wpdmdl(clean_url)
                if not wpdmdl:
                    continue

                if wpdmdl not in docs:
                    docs[wpdmdl] = {
                        "wpdmdl": wpdmdl,
                        "title": title,
                        "url": clean_url,
                        "update_date": update_date,
                        "category": category,
                        "page": page_path,
                    }

            logger.info("Page %s: found %d docs so far (%d unique)",
                        page_path, len(rows), len(docs))
            time.sleep(1.5)

        logger.info("Total unique documents discovered: %d", len(docs))
        return list(docs.values())

    def _extract_pdf(self, url: str) -> Optional[str]:
        try:
            resp = self.http.get(url, timeout=90)
        except Exception as e:
            logger.warning("PDF fetch error: %s (%s)", url[:90], e)
            return None
        if resp.status_code != 200:
            logger.warning("PDF HTTP %d: %s", resp.status_code, url[:90])
            return None
        data = resp.content
        if not data or not data[:5].startswith(b"%PDF"):
            logger.info("Not a PDF: %s", url[:90])
            return None
        if len(data) > MAX_PDF_BYTES:
            logger.info("Skip oversized PDF (%d bytes): %s", len(data), url[:90])
            return None
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                parts = [(p.extract_text() or "") for p in pdf.pages[:MAX_PDF_PAGES]]
        except Exception as e:
            logger.warning("PDF parse error: %s (%s)", url[:90], e)
            return None
        return _clean_text("\n".join(parts))

    def _build(self, doc: dict) -> Optional[dict]:
        text = self._extract_pdf(doc["url"])
        if not text or not _is_clean(text):
            logger.info("Skip (no/low text): %s", doc["title"][:60])
            return None
        title = doc["title"] or "NAMFISA document"
        return {
            "_id": f"na-namfisa-{doc['wpdmdl']}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": _parse_date(text, doc.get("update_date")),
            "url": doc["url"],
            "category": doc["category"],
            "doc_type": _classify_doc_type(title),
            "language": "en",
        }

    # ── BaseScraper interface ───────────────────────────────────────────

    def fetch_all(self) -> Generator[dict, None, None]:
        for doc in self._crawl_documents():
            rec = self._build(doc)
            if rec:
                yield rec
            time.sleep(1.5)

    def fetch_updates(self, since: Optional[str] = None) -> Generator[dict, None, None]:
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        return raw


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="NA/NAMFISA-Instruments scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test-api"])
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    scraper = NAMFISAInstrumentsScraper()

    if args.command == "test-api":
        docs = scraper._crawl_documents()
        logger.info("Total unique document links: %d", len(docs))
        for d in docs[:15]:
            logger.info("  [%s] %s — %s", d["wpdmdl"], d["title"][:55], d["category"])
        return

    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    limit = 15 if args.sample else None
    count = 0
    for record in scraper.fetch_all():
        count += 1
        if args.sample or count <= 15:
            with open(sample_dir / f"{count:04d}.json", "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info("[%d] %s — %d chars (%s)", count,
                    record["title"][:55], len(record["text"]), record.get("date"))
        if limit and count >= limit:
            break
    logger.info("Done: %d records", count)


if __name__ == "__main__":
    main()
