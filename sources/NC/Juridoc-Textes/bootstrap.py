#!/usr/bin/env python3
"""
NC/Juridoc-Textes -- New Caledonia consolidated legal texts (Juridoc)

Fetches the consolidated legal texts ("Textes consolidés") published by the
Government of New Caledonia on juridoc.gouv.nc. This collection contains the
Lois du pays, the consolidated New Caledonian codes (code civil applicable en
NC, code du travail, code des impôts, etc.) and other institutional texts, each
as a born-digital PDF with extractable full text.

Access:
  The site runs on Lotus Domino. The RSS view exposes every entry through
  ReadViewEntries, which returns one <viewentry> per document with an embedded
  RSS <item> (title, PDF link, theme). We enumerate that view, download each
  PDF and extract the text with PyMuPDF.

  NOTE: the published links use the host `www.juridoc.gouv.nc`, whose TLS cert
  is only valid for the bare `juridoc.gouv.nc`. We normalize the host before
  downloading to avoid certificate-hostname-mismatch errors.

Data:
  - ~91 consolidated texts (Lois du pays, NC codes, institutional texts)
  - Full text extracted from born-digital PDFs (tens of thousands of chars each)
  - French language

Usage:
  python bootstrap.py bootstrap --sample   # Fetch 10+ sample records
  python bootstrap.py bootstrap            # Full pull (writes data/records.jsonl)
  python bootstrap.py bootstrap-fast       # Alias for full pull (VPS pipeline)
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import io
import re
import json
import html
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, List

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NC.Juridoc-Textes")

import fitz  # PyMuPDF

SOURCE_ID = "NC/Juridoc-Textes"
DB = "JdTextes"
# Cert-valid host (the published links use www., whose cert is invalid).
HOST = "juridoc.gouv.nc"
VIEW_URL = f"https://{HOST}/JuriDoc/{DB}.nsf/rss.xml?ReadViewEntries&Start=1&Count=2000"

FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def normalize_host(url: str) -> str:
    """Rewrite www.juridoc.gouv.nc -> juridoc.gouv.nc and force https."""
    url = url.replace("http://", "https://")
    url = url.replace("https://www.juridoc.gouv.nc", f"https://{HOST}")
    return url


def parse_french_date(title: str) -> str:
    """Extract an ISO date from a French text title (e.g. 'du 21 mai 2026')."""
    m = re.search(r"du\s+(\d{1,2})(?:er)?\s+([a-zûéèêà]+)\s+(\d{4})", title, re.I)
    if m:
        day = int(m.group(1))
        month = FRENCH_MONTHS.get(m.group(2).lower())
        year = int(m.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    m = re.search(r"\b(\d{4})\b", title)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        t = page.get_text()
        if t:
            parts.append(t)
    doc.close()
    text = "\n".join(parts)
    # Collapse runs of blank lines / trailing spaces
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class JuridocTextesScraper(BaseScraper):
    """Scraper for NC/Juridoc-Textes — New Caledonia consolidated legal texts."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "*/*",
        })

    def _list_entries(self) -> List[Dict[str, Any]]:
        """Enumerate all documents in the RSS view via ReadViewEntries."""
        resp = self.session.get(VIEW_URL, timeout=90)
        resp.raise_for_status()
        xml = resp.content.decode("utf-8", "replace")
        entries = []
        for m in re.finditer(
            r'<viewentry\b[^>]*\bunid="([0-9A-F]+)".*?<text>(.*?)</text>',
            xml, re.S,
        ):
            unid = m.group(1)
            item = html.unescape(m.group(2))
            tm = re.search(r"<title>(.*?)</title>", item, re.S)
            lm = re.search(r"<link>(.*?)</link>", item, re.S)
            dm = re.search(r"<description>(.*?)</description>", item, re.S)
            if not (tm and lm):
                continue
            entries.append({
                "unid": unid,
                "title": html.unescape(tm.group(1)).strip(),
                "pdf_url": normalize_host(html.unescape(lm.group(1)).strip()),
                "theme": html.unescape(dm.group(1)).replace("Thème(s) :", "").strip() if dm else None,
            })
        return entries

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        limit = 12 if sample else None
        logger.info(f"Enumerating {DB} view...")
        entries = self._list_entries()
        logger.info(f"  Found {len(entries)} documents")
        count = 0
        for entry in entries:
            if limit and count >= limit:
                break
            self.rate_limiter.wait()
            try:
                resp = self.session.get(entry["pdf_url"], timeout=120)
                resp.raise_for_status()
                if not resp.content or len(resp.content) < 200:
                    logger.warning(f"  Empty/short PDF: {entry['title'][:50]}")
                    continue
                text = extract_pdf_text(resp.content)
            except Exception as e:
                logger.error(f"  Failed {entry['title'][:50]}: {e}")
                continue
            if len(text) < 200:
                logger.warning(f"  Too little text ({len(text)} chars): {entry['title'][:50]}")
                continue
            entry["text"] = text
            count += 1
            logger.info(f"  [{count}] {len(text)} chars — {entry['title'][:60]}")
            yield entry
        logger.info(f"Fetched {count} consolidated texts")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(sample=False)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        title = raw.get("title", "")
        return {
            "_id": f"{SOURCE_ID}/{raw['unid']}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": now,
            "title": title,
            "text": raw.get("text", ""),
            "date": parse_french_date(title),
            "url": raw["pdf_url"],
            "doc_id": raw["unid"],
            "theme": raw.get("theme"),
            "language": "fr",
        }

    def write_jsonl(self) -> int:
        """Full pull → data/records.jsonl (used by the VPS pipeline)."""
        out_dir = Path(__file__).parent / "data"
        out_dir.mkdir(exist_ok=True)
        path = out_dir / "records.jsonl"
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for raw in self.fetch_all(sample=False):
                rec = self.normalize(raw)
                if not rec or not rec.get("text"):
                    continue
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
                if count % 25 == 0:
                    f.flush()
        logger.info(f"Wrote {count} records to {path}")
        print("BOOTSTRAP_COMPLETE")
        return count

    def test_connection(self) -> bool:
        entries = self._list_entries()
        logger.info(f"Connectivity OK — {len(entries)} documents in view")
        return len(entries) > 0


if __name__ == "__main__":
    scraper = JuridocTextesScraper()
    command = sys.argv[1] if len(sys.argv) > 1 else "bootstrap"
    sample_mode = "--sample" in sys.argv

    if command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)
    elif command == "bootstrap-fast":
        n = scraper.write_jsonl()
        sys.exit(0 if n > 0 else 1)
    elif command == "bootstrap":
        if sample_mode:
            scraper.bootstrap(sample_mode=True, sample_size=10)
        else:
            scraper.write_jsonl()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
