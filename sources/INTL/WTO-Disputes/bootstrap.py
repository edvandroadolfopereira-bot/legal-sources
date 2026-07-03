#!/usr/bin/env python3
"""
INTL/WTO-Disputes -- WTO Dispute Settlement: Panel & Appellate Body Reports

Fetches the full text of adopted panel reports, Appellate Body reports,
compliance-panel reports and arbitration awards for modern WTO disputes
(DS1-present, 1995-onwards). Distinct from INTL/GATT-Disputes (1947-1995).

Access path (all public, no auth):
  1. WTO Documents Online XML API lists the documents filed under a dispute:
       https://docs.wto.org/dol2fe/Pages/SS/GetXMLResults.aspx
         ?DataSource=Cat&query=@Symbol=WT/DS{N}/*&Language=English
     Each <DOCUMENT> carries SYMBOL, CATID, FILENAMESA (file path),
     RESTRICTIONTYPENAME (U=unrestricted, D=de-restricted, R=restricted)
     and ISSUINGDATE.
  2. Report documents are identified by their symbol suffix:
       WT/DS{N}/R        panel report
       WT/DS{N}/AB/R     Appellate Body report
       WT/DS{N}/RW[n]    compliance (Art. 21.5) panel report
       WT/DS{N}/AB/RW[n] compliance Appellate Body report
       WT/DS{N}/ARB[..]  arbitration award (Art. 22.6 / 25)
  3. Each report PDF is downloaded from:
       https://docs.wto.org/dol2fe/Pages/FE_Search/ExportFile.aspx
         ?Id={CATID}&filename={path}&Open=True
     and the full text extracted with pdfplumber.
  4. The per-dispute case page (cases_e/ds{N}_e.htm) supplies the dispute
     title and the Secretariat's narrative summary, which is prepended.

Only disputes that reached at least one publicly-available report are yielded
(consultation-only / settled disputes have no adjudicative full text).

Usage:
  python bootstrap.py bootstrap --sample   # 15 sample records
  python bootstrap.py bootstrap            # all disputes
  python bootstrap.py bootstrap-fast       # concurrent full run
  python bootstrap.py test                 # connectivity test
"""

import sys
import logging
import re
import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.WTO-Disputes")

WTO_BASE = "https://www.wto.org"
DOCS_BASE = "https://docs.wto.org"
API_URL = f"{DOCS_BASE}/dol2fe/Pages/SS/GetXMLResults.aspx"
EXPORT_URL = f"{DOCS_BASE}/dol2fe/Pages/FE_Search/ExportFile.aspx"

# Highest DS number to probe. WTO is around DS630 in 2026; pad for headroom.
MAX_DS = 640
# Skip oversized PDFs (bytes) to stay within time/disk budget.
MAX_PDF_BYTES = 40 * 1024 * 1024
# Cap report documents downloaded per dispute.
MAX_REPORTS_PER_DISPUTE = 8

# Symbol suffix => human label for report-type documents.
REPORT_PATTERNS = [
    (re.compile(r"/AB/RW\d*$"), "Compliance Appellate Body Report"),
    (re.compile(r"/AB/R$"), "Appellate Body Report"),
    (re.compile(r"/RW\d*$"), "Compliance Panel Report"),
    (re.compile(r"/R$"), "Panel Report"),
    (re.compile(r"/ARB\d*$"), "Arbitration Award"),
    (re.compile(r"/AB-\d+/ARB"), "Arbitration Award"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{WTO_BASE}/english/tratop_e/dispu_e/dispu_status_e.htm",
}


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _classify_report(symbol: str) -> Optional[str]:
    """Return a report label if `symbol` is a panel/AB/compliance/arb report."""
    for pat, label in REPORT_PATTERNS:
        if pat.search(symbol):
            return label
    return None


def _export_filename(filenamesa: str) -> str:
    """Convert a FILENAMESA value (e.g. 'Q:/WT/DS/8R.pdf') to the ExportFile
    `filename` query value (e.g. 'q/WT/DS/8R.pdf'). Multi-file values are
    separated by '#'; take the first."""
    raw = filenamesa.split("#")[0].strip()
    # 'Q:/WT/DS/8R.pdf' -> drive letter lowercased, colon dropped.
    if len(raw) >= 3 and raw[1] == ":":
        return raw[0].lower() + raw[2:]
    return raw


def _parse_iso_date(raw: str) -> Optional[str]:
    """ISSUINGDATE is 'DD/MM/YYYY 00:00:00' or 'YYYY-MM-DD...'."""
    raw = (raw or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


class WTODisputesScraper(BaseScraper):
    """Scraper for INTL/WTO-Disputes."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _request(self, url: str, timeout: int = 60, stream: bool = False,
                 params: dict = None) -> Optional[requests.Response]:
        for attempt in range(3):
            try:
                time.sleep(1.5)
                resp = self.session.get(url, timeout=timeout, stream=stream,
                                        params=params)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url[:80]}: {e}")
                if attempt < 2:
                    time.sleep(4 * (attempt + 1))
        return None

    # ---- document listing ------------------------------------------------

    def _list_documents(self, ds_num: int) -> List[Dict[str, Any]]:
        """Query the DOL XML API for all documents under WT/DS{N}/*."""
        resp = self._request(
            API_URL,
            params={
                "DataSource": "Cat",
                "query": f"@Symbol=WT/DS{ds_num}/*",
                "Language": "English",
            },
            timeout=50,
        )
        if resp is None:
            return []

        soup = BeautifulSoup(resp.content, "xml")
        docs = []
        for doc in soup.find_all("DOCUMENT"):
            def field(tag):
                el = doc.find(tag)
                return el.get_text(strip=True) if el else ""

            symbol_raw = field("CATTITLE")  # fallback; real symbol below
            symbol = ""
            sym_el = doc.find("SYMBOL")
            if sym_el:
                symbol = sym_el.get_text(strip=True)
            # SYMBOL may bundle joint disputes with '#': WT/DS8/R#WT/DS10/R...
            primary_symbol = symbol.split("#")[0].strip()

            docs.append({
                "symbol": primary_symbol,
                "all_symbols": symbol,
                "catid": field("CATID"),
                "filename": field("FILENAMESA"),
                "restriction": field("RESTRICTIONTYPENAME"),
                "title": field("CATTITLE"),
                "date": _parse_iso_date(field("ISSUINGDATE")),
            })
        return docs

    # ---- case page -------------------------------------------------------

    def _fetch_case_page(self, ds_num: int) -> Dict[str, str]:
        """Return {'title', 'summary'} from the dispute's case page."""
        url = f"{WTO_BASE}/english/tratop_e/dispu_e/cases_e/ds{ds_num}_e.htm"
        resp = self._request(url, timeout=40)
        if resp is None:
            return {"title": "", "summary": "", "url": url}

        html = resp.content.decode("latin-1", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        # Title: the text after the "DS{n}:" span heading.
        title = ""
        m = re.search(r'class="dsnumber">DS.*?:</span>(.*?)</h\d', html,
                      re.S | re.I)
        if m:
            title = BeautifulSoup(m.group(1), "html.parser").get_text(" ", strip=True)
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        title = re.sub(r"\s+", " ", title).strip(" -|")

        # Summary: body text under "Summary of the dispute to date".
        body = soup.find("body")
        summary = ""
        if body:
            for tag in body.find_all(["script", "style", "nav", "footer"]):
                tag.decompose()
            full = body.get_text("\n", strip=True)
            idx = full.lower().find("summary of the dispute")
            if idx >= 0:
                summary = full[idx:]
                # Trim trailing site boilerplate.
                for stop in ["Share\nFollow this dispute", "Problems viewing",
                             "RSS feed", "back to top\nback to top"]:
                    j = summary.find(stop)
                    if j > 0:
                        summary = summary[:j]
                summary = _clean(summary)

        return {"title": title, "summary": summary, "url": url}

    # ---- PDF text --------------------------------------------------------

    def _extract_pdf_text(self, catid: str, filename: str) -> Optional[str]:
        url = EXPORT_URL
        resp = self._request(
            url, timeout=120, stream=True,
            params={"Id": catid, "filename": _export_filename(filename),
                    "Open": "True"},
        )
        if resp is None:
            return None

        clen = resp.headers.get("Content-Length")
        if clen and int(clen) > MAX_PDF_BYTES:
            logger.warning(f"Skipping oversized PDF (cat {catid}, {clen} bytes)")
            return None

        ctype = resp.headers.get("Content-Type", "")
        if "pdf" not in ctype.lower():
            logger.warning(f"Not a PDF (cat {catid}): {ctype}")
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                size = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        logger.warning(f"PDF exceeded cap mid-stream (cat {catid})")
                        return None
                    tmp.write(chunk)
                tmp.flush()

                with pdfplumber.open(tmp.name) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages]
            text = _clean("\n\n".join(pages))
            return text if len(text) >= 200 else None
        except Exception as e:
            logger.warning(f"PDF extraction failed (cat {catid}): {e}")
            return None

    # ---- core ------------------------------------------------------------

    def _build_raw(self, ds_num: int) -> Optional[Dict[str, Any]]:
        """Assemble a raw record for a dispute, or None if it has no public
        report. Heavy PDF downloads are deferred to normalize()."""
        docs = self._list_documents(ds_num)
        if not docs:
            return None

        reports = []
        for d in docs:
            label = _classify_report(d["symbol"])
            if not label:
                continue
            if d["restriction"] not in ("U", "D"):  # skip member-restricted
                continue
            if not d["catid"] or not d["filename"]:
                continue
            reports.append({**d, "label": label})

        if not reports:
            return None

        # Order reports chronologically; cap count.
        reports.sort(key=lambda r: r["date"] or "9999")
        reports = reports[:MAX_REPORTS_PER_DISPUTE]

        case = self._fetch_case_page(ds_num)

        return {
            "ds_num": ds_num,
            "title": case["title"] or f"WTO Dispute DS{ds_num}",
            "summary": case["summary"],
            "case_url": case["url"],
            "reports": reports,
        }

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        ds_num = raw["ds_num"]
        parts = [f"WTO Dispute Settlement — DS{ds_num}"]
        parts.append(f"Title: {raw['title']}")
        if raw.get("summary"):
            parts.append("\n--- Summary of the dispute ---\n" + raw["summary"])

        report_symbols = []
        report_dates = []
        for rep in raw["reports"]:
            text = self._extract_pdf_text(rep["catid"], rep["filename"])
            if not text:
                continue
            report_symbols.append(rep["symbol"])
            if rep["date"]:
                report_dates.append(rep["date"])
            header = f"\n--- {rep['label']} ({rep['symbol']}) ---\n"
            parts.append(header + text)

        full_text = _clean("\n".join(parts))

        # Decision date: prefer the latest report date.
        date = max(report_dates) if report_dates else None

        return {
            "_id": f"WT-DS{ds_num}",
            "_source": "INTL/WTO-Disputes",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": full_text,
            "date": date,
            "url": raw["case_url"],
            "dispute_number": ds_num,
            "report_symbols": report_symbols,
            "report_count": len(report_symbols),
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        count = 0
        for ds_num in range(1, MAX_DS + 1):
            if ds_num % 50 == 0:
                logger.info(f"Progress: probing DS{ds_num} ({count} with reports)")
            try:
                raw = self._build_raw(ds_num)
            except Exception as e:
                logger.warning(f"DS{ds_num} failed: {e}")
                continue
            if raw is None:
                continue
            count += 1
            yield raw
        logger.info(f"Completed: {count} disputes with public reports")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def test(self) -> bool:
        docs = self._list_documents(8)
        if not docs:
            logger.error("API returned no documents for DS8")
            return False
        reports = [d for d in docs if _classify_report(d["symbol"])]
        logger.info(f"DS8: {len(docs)} docs, {len(reports)} reports "
                    f"(e.g. {[r['symbol'] for r in reports[:3]]})")
        return len(reports) > 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/WTO-Disputes data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true",
                        help="Fetch a small sample (validation)")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = WTODisputesScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)

    elif args.command in ("bootstrap", "bootstrap-fast"):
        if args.command == "bootstrap-fast" and not args.sample:
            stats = scraper.bootstrap_fast()
        else:
            stats = scraper.bootstrap(sample_mode=args.sample, sample_size=15)
        fetched = stats.get("records_fetched", 0) or stats.get("sample_records_saved", 0)
        logger.info(f"Bootstrap complete: {fetched} records — {stats}")
        if fetched == 0:
            sys.exit(1)

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {stats}")


if __name__ == "__main__":
    main()
