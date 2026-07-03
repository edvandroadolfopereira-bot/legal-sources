#!/usr/bin/env python3
"""
PR/TribunalSupremo -- Puerto Rico Supreme Court Opinions (Tribunal Supremo)

Fetches full-text opinions of the Supreme Court of Puerto Rico from the
official Rama Judicial site (dts.poderjudicial.pr).

Strategy:
  - Iterate year index pages: /opiniones/{YEAR}/{YEAR}.htm  (1998-present)
  - Each year page links every opinion as a PDF. Two URL schemes appear:
      * newer years (2012+): absolute  /ts/{YEAR}/{YEAR}tspr{NNN}.pdf
      * older years         : relative {YEAR}TSPR{NNN}.pdf (resolved by urljoin)
  - Download each PDF and extract full text via pdfplumber (PyMuPDF fallback)
  - Parse citation / case number / date / parties from the PDF header, which is
    consistent: "EN EL TRIBUNAL SUPREMO DE PUERTO RICO" ... "YYYY TSPR NNN" ...
    "Número del Caso:" ... "Fecha:"

  fetch_all() yields RAW dicts; the framework calls normalize() (which performs
  the PDF download + extraction) and streams records to data/records.jsonl.

Usage:
  python bootstrap.py test                  # connectivity test
  python bootstrap.py bootstrap --sample    # 15 sample records to sample/
  python bootstrap.py bootstrap-fast --full # full pull -> data/records.jsonl
  python bootstrap.py update                # current-year opinions
"""

import sys
import io
import re
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from urllib.parse import urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PR.TribunalSupremo")

BASE = "https://dts.poderjudicial.pr"
# Opinions are archived from 1998 onward; iterate a generous range and skip 404s.
FIRST_YEAR = 1998

SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Matches both absolute and relative PDF links to opinions, e.g.
#   /ts/2020/2020tspr156.pdf  or  2005TSPR168.pdf
PDF_LINK_RE = re.compile(r'href="([^"]*?(\d{4})tspr(\d+)\.pdf)"', re.IGNORECASE)
CITATION_RE = re.compile(r"(\d{4})\s*TSPR\s*(\d+)", re.IGNORECASE)
CASENUM_RE = re.compile(r"N[uú]mero\s+del\s+Caso:\s*([^\n]+)")
FECHA_RE = re.compile(r"Fecha:\s*([^\n]+)")
# "17 de diciembre de 2020"  or  "22/diciembre/2000"
DATE_TXT_RE = re.compile(r"(\d{1,2})\s*(?:de\s+|/)\s*(\w+?)\s*(?:\s+de\s+|/)\s*(\d{4})")
# "22/12/2000"
DATE_NUM_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# Caption lines that are procedural/role labels, not party names.
_ROLE_STOP = re.compile(
    r"^(demandante|demandada|demandado|peticionari[oa]|recurrid[oa]|recurrente|"
    r"querellad[oa]|querellante|apelante|apelad[oa]|promovente|promovid[oa]|"
    r"acusad[oa]|certiorari|apelaci[oó]n|revisi[oó]n|certificaci[oó]n|"
    r"interventor[a]?|opositor[a]?|parte[s]?|consolidad[oa]s?|"
    r"[a-zñáéíóú\- ]*-(peticionari[oa]|recurrid[oa]|recurrente|apelante|apelad[oa]))$",
    re.IGNORECASE,
)


class TribunalSupremoScraper(BaseScraper):
    """Scraper for PR/TribunalSupremo -- Puerto Rico Supreme Court opinions."""

    def __init__(self):
        super().__init__(Path(__file__).parent)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/worldwidelaw/legal-sources)",
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            "Accept-Language": "es-PR,es;q=0.9,en;q=0.5",
        })

    # ── HTTP helpers ──────────────────────────────────────────────────
    def _get(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(1)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429:
                    logger.warning("Rate limited, sleeping 30s")
                    time.sleep(30)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(8)
        return None

    # ── Year index parsing ────────────────────────────────────────────
    def _year_opinions(self, year: int) -> List[Dict[str, Any]]:
        """Return list of {url, year, num} for every opinion linked on a year page."""
        page_url = f"{BASE}/opiniones/{year}/{year}.htm"
        resp = self._get(page_url)
        if resp is None:
            return []
        html = resp.text
        seen = set()
        out = []
        for m in PDF_LINK_RE.finditer(html):
            href, doc_year, num = m.group(1), m.group(2), m.group(3)
            abs_url = urljoin(page_url, href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            out.append({
                "url": abs_url,
                "year": int(doc_year),
                "num": int(num),
            })
        return out

    # ── PDF text extraction ───────────────────────────────────────────
    @staticmethod
    def _extract_pdf(pdf_bytes: bytes) -> str:
        text = ""
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                parts = [(p.extract_text() or "") for p in pdf.pages]
            text = "\n".join(parts)
        except Exception as e:
            logger.debug(f"pdfplumber failed: {e}")
        if len(text.strip()) < 100:
            try:
                import fitz  # PyMuPDF
                d = fitz.open(stream=pdf_bytes, filetype="pdf")
                text = "\n".join(d[i].get_text() for i in range(len(d)))
            except Exception as e:
                logger.debug(f"PyMuPDF failed: {e}")
        # Tidy whitespace
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _parse_date(text: str) -> str:
        m = FECHA_RE.search(text)
        scope = m.group(1) if m else text[:600]
        dm = DATE_TXT_RE.search(scope)
        if dm:
            day = int(dm.group(1))
            month = SPANISH_MONTHS.get(dm.group(2).lower())
            year = int(dm.group(3))
            if month:
                try:
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    pass
        nm = DATE_NUM_RE.search(scope)
        if nm:
            day, month, year = int(nm.group(1)), int(nm.group(2)), int(nm.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        return ""

    @staticmethod
    def _parse_title(text: str, citation: str) -> str:
        """Build a party caption from the block above 'Número del Caso'."""
        head = text
        cm = CASENUM_RE.search(text)
        if cm:
            head = text[:cm.start()]
        # Cut everything before the standard court header line (drops the
        # leading case-number + footnote marker, e.g. "CC-99-312 1").
        hm = re.search(r"EN EL TRIBUNAL SUPREMO DE PUERTO RICO", head, re.IGNORECASE)
        if hm:
            head = head[hm.end():]
        head = CITATION_RE.sub("\n", head)
        head = re.sub(r"\d+\s*DPR\s*_*", "", head)

        parts = []
        for raw_line in head.splitlines():
            line = raw_line.strip(" .,;\t")
            if not line:
                continue
            # Drop lone footnote/page markers and pure-digit lines
            if re.fullmatch(r"\d{1,3}", line):
                continue
            # Drop "v." separators but remember them
            if re.fullmatch(r"v\.?|vs\.?|y", line, re.IGNORECASE):
                if parts and parts[-1] != "v.":
                    parts.append("v.")
                continue
            # Drop procedural / role-label lines
            if _ROLE_STOP.match(line):
                continue
            parts.append(line)
            if len(parts) >= 6:
                break

        caption = " ".join(parts).strip(" .,-v")
        caption = re.sub(r"\s+", " ", caption)
        if len(caption) > 240:
            caption = caption[:240].rsplit(" ", 1)[0]
        if len(caption) < 3:
            caption = citation
        return caption

    # ── Framework contract ────────────────────────────────────────────
    def normalize(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = raw["url"]
        resp = self._get(url)
        if resp is None or not resp.content:
            logger.warning(f"PDF fetch failed: {url}")
            return None
        text = self._extract_pdf(resp.content)
        if len(text) < 200:
            logger.warning(f"Insufficient text ({len(text)} chars): {url}")
            return None

        cm = CITATION_RE.search(text)
        if cm:
            citation = f"{cm.group(1)} TSPR {int(cm.group(2))}"
        else:
            citation = f"{raw['year']} TSPR {raw['num']}"

        casenum = ""
        cn = CASENUM_RE.search(text)
        if cn:
            casenum = re.sub(r"\s+", " ", cn.group(1)).strip()

        date = self._parse_date(text)
        title = self._parse_title(text, citation)
        doc_id = f"PR-TSPR-{raw['year']}-{raw['num']:04d}"

        return {
            "_id": doc_id,
            "_source": "PR/TribunalSupremo",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "citation": citation,
            "case_number": casenum,
            "court": "Tribunal Supremo de Puerto Rico",
            "url": url,
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        current = datetime.now(timezone.utc).year
        seen = set()
        for year in range(FIRST_YEAR, current + 1):
            ops = self._year_opinions(year)
            if not ops:
                logger.info(f"Year {year}: no opinions (page missing or empty)")
                continue
            logger.info(f"Year {year}: {len(ops)} opinions")
            for op in ops:
                key = (op["year"], op["num"])
                if key in seen:
                    continue
                seen.add(key)
                yield op

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        current = datetime.now(timezone.utc).year
        for op in self._year_opinions(current):
            yield op

    def test(self) -> bool:
        ops = self._year_opinions(2020)
        if not ops:
            logger.error("No opinions found for 2020")
            return False
        logger.info(f"Index OK: {len(ops)} opinions for 2020")
        rec = self.normalize(ops[0])
        if not rec or len(rec.get("text", "")) < 200:
            logger.error("Could not extract opinion full text")
            return False
        logger.info(
            f"Doc OK: {rec['citation']} | {rec['title'][:60]} "
            f"({len(rec['text']):,} chars, date={rec['date']})"
        )
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PR/TribunalSupremo data fetcher")
    parser.add_argument(
        "command",
        choices=["test", "bootstrap", "bootstrap-fast", "update"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch a small sample")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = TribunalSupremoScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)

    elif args.command == "bootstrap":
        if args.sample:
            stats = scraper.run_sample(n=15)
        else:
            stats = scraper.bootstrap_fast()
        logger.info(f"Done: {stats}")

    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap_fast()
        logger.info(f"Done: {stats}")

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Done: {stats}")


if __name__ == "__main__":
    main()
