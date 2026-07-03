#!/usr/bin/env python3
"""
NC/Juridoc-Juris -- New Caledonia jurisprudence (Juridoc)

Fetches jurisprudence published by the Government of New Caledonia on
juridoc.gouv.nc — chiefly decisions of the Tribunal administratif de
Nouvelle-Calédonie (plus occasional Conseil d'État rulings concerning NC), each
as a born-digital PDF with extractable full text.

Access:
  The site runs on Lotus Domino. The RSS view exposes every decision through
  ReadViewEntries, which returns one <viewentry> per document with an embedded
  RSS <item> (title, PDF link, matière). We enumerate that view, download each
  PDF and extract the text with PyMuPDF.

  NOTE: the published links use the host `www.juridoc.gouv.nc`, whose TLS cert
  is only valid for the bare `juridoc.gouv.nc`. We normalize the host before
  downloading to avoid certificate-hostname-mismatch errors.

Data:
  - ~103 decisions (Tribunal administratif de NC, Conseil d'État)
  - Full text extracted from born-digital PDFs
  - French language

Usage:
  python bootstrap.py bootstrap --sample   # Fetch 10+ sample records
  python bootstrap.py bootstrap            # Full pull (writes data/records.jsonl)
  python bootstrap.py bootstrap-fast       # Alias for full pull (VPS pipeline)
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
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
logger = logging.getLogger("legal-data-hunter.NC.Juridoc-Juris")

import fitz  # PyMuPDF

SOURCE_ID = "NC/Juridoc-Juris"
DB = "JdJuris"
HOST = "juridoc.gouv.nc"
VIEW_URL = f"https://{HOST}/JuriDoc/{DB}.nsf/rss.xml?ReadViewEntries&Start=1&Count=5000"


def normalize_host(url: str) -> str:
    url = url.replace("http://", "https://")
    url = url.replace("https://www.juridoc.gouv.nc", f"https://{HOST}")
    return url


def parse_date(title: str) -> str:
    """Extract ISO date from 'du DD/MM/YYYY'."""
    m = re.search(r"du\s+(\d{1,2})/(\d{1,2})/(\d{4})", title)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def parse_court(title: str) -> str:
    return title.split(":")[0].strip() if ":" in title else None


def parse_decision_no(title: str) -> str:
    m = re.search(r"n[°º]\s*([\w./-]+)", title)
    return m.group(1) if m else None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        t = page.get_text()
        if t:
            parts.append(t)
    doc.close()
    text = "\n".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class JuridocJurisScraper(BaseScraper):
    """Scraper for NC/Juridoc-Juris — New Caledonia jurisprudence."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "*/*",
        })

    def _list_entries(self) -> List[Dict[str, Any]]:
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
                "matiere": html.unescape(dm.group(1)).replace("Matière :", "").strip() if dm else None,
            })
        return entries

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        limit = 12 if sample else None
        logger.info(f"Enumerating {DB} view...")
        entries = self._list_entries()
        logger.info(f"  Found {len(entries)} decisions")
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
        logger.info(f"Fetched {count} decisions")

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all(sample=False)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        title = raw.get("title", "")
        return {
            "_id": f"{SOURCE_ID}/{raw['unid']}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": now,
            "title": title,
            "text": raw.get("text", ""),
            "date": parse_date(title),
            "url": raw["pdf_url"],
            "doc_id": raw["unid"],
            "court": parse_court(title),
            "decision_number": parse_decision_no(title),
            "matiere": raw.get("matiere"),
            "language": "fr",
        }

    def write_jsonl(self) -> int:
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
        logger.info(f"Connectivity OK — {len(entries)} decisions in view")
        return len(entries) > 0


if __name__ == "__main__":
    scraper = JuridocJurisScraper()
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
