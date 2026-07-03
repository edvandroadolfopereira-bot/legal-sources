#!/usr/bin/env python3
"""
LB/BCCL — Banking Control Commission of Lebanon Circulars

Fetches regulatory circulars from the BCCL website.

Strategy:
  1. Fetch the circulars HTML page and parse the TablePress table
     for metadata (date, number, description, addressee, PDF URL)
  2. Download each Arabic PDF
  3. Extract full text via pdfplumber

If the main page is unavailable (503), falls back to probing known
PDF URL patterns directly.

Data:
  - ~90+ circulars from 1967-2025
  - Language: Arabic (PDFs), English (metadata)
  - License: Lebanese government publication

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://bccl.gov.lb"
SOURCE_ID = "LB/BCCL"
SAMPLE_DIR = Path(__file__).parent / "sample"
REQUEST_DELAY = 2.0


# ── HTML table parser ──────────────────────────────────────────────

class _TableParser(HTMLParser):
    """Parse a TablePress HTML table into rows of cells."""

    def __init__(self):
        super().__init__()
        self.rows: List[List[str]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self._current_href: Optional[str] = None
        self._cell_href: Optional[str] = None
        self._skip_header = True

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self._in_table = True
        elif tag == "thead":
            self._skip_header = True
        elif tag == "tbody":
            self._skip_header = False
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in ("td", "th") and self._in_row:
            self._in_cell = True
            self._current_cell = []
            self._cell_href = None
        elif tag == "a" and self._in_cell:
            href = attrs_dict.get("href", "")
            if href.endswith(".pdf"):
                self._cell_href = href
        elif tag == "br" and self._in_cell:
            self._current_cell.append("; ")

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if not self._skip_header and self._current_row:
                self.rows.append(self._current_row)
        elif tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            cell_text = "".join(self._current_cell).strip()
            if self._cell_href:
                cell_text = self._cell_href
            self._current_row.append(cell_text)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)


def parse_circulars_table(html_content: str) -> List[Dict[str, str]]:
    """Parse the circulars HTML table into a list of circular metadata dicts."""
    parser = _TableParser()
    parser.feed(html_content)
    circulars = []
    for row in parser.rows:
        if len(row) < 5:
            continue
        date_str = row[0].strip()
        number = row[1].strip()
        description = row[2].strip()
        addressee = row[3].strip()
        pdf_url = row[4].strip()
        if not pdf_url.startswith("http"):
            if pdf_url.startswith("/"):
                pdf_url = BASE_URL + pdf_url
            elif pdf_url.endswith(".pdf"):
                pdf_url = BASE_URL + "/" + pdf_url
            else:
                pdf_url = ""
        circulars.append({
            "date": date_str,
            "number": number,
            "description": description,
            "addressee": addressee,
            "pdf_url": pdf_url,
        })
    return circulars


# ── PDF extraction ─────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    if not HAS_PDF:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(pages)
    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return ""


# ── Fetching ───────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal research; open data)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def fetch_circulars_page(session: requests.Session) -> Optional[str]:
    """Try to fetch the live circulars HTML page."""
    url = f"{BASE_URL}/circulars/"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.text
        logger.warning("Circulars page returned %d", resp.status_code)
    except Exception as e:
        logger.warning("Failed to fetch circulars page: %s", e)
    return None


# Known circulars from the archived page (fallback when site is 503)
KNOWN_CIRCULARS = [
    ("2025/12/26", "302", "Periodic templates required by the Banking Control Commission of Lebanon",
     "Banks; Financial Institutions", "BCCLCircularNo302.pdf"),
    ("2025/07/29", "301", "Appointment of Chairman and Board Members of the BCCL",
     "Banks; Specialized Lending Entities (Credit Counters); Financial Institutions; Exchange Institutions; External Auditors; Institutions Engaged with Electronic Financial Operations; Other Institutions", "BCCLCircularNo301.pdf"),
    ("2024/02/07", "4", "Foreign Exchange Positions",
     "Financial Institutions; External Auditors", "BCCLCircularNo4.pdf"),
    ("2023/11/27", "300", "Foreign Exchange Positions",
     "Banks; External Auditors", "BCCLCircularNo300.pdf"),
    ("2021/09/03", "1-IEF", "Implementation of BCCL circular 222 and 272 by Institutions Engaged with Electronic Financial Operations",
     "Institutions Engaged with Electronic Financial Operations", "BCCLCircularNo1IEF.pdf"),
    ("2020/10/01", "299", "Computation of Capital Adequacy Ratios",
     "Banks; External Auditors", "BCCLCircularNo299.pdf"),
    ("2020/06/16", "298", "Appointment of Chairman and Board Members of the BCCL",
     "Banks; Financial Institutions; Exchange Institutions; External Auditors", "BCCLCircularNo298.pdf"),
    ("2018/09/13", "297", "Computation of LBP Loan to Deposits Ratio",
     "Banks", "BCCLCircularNo297.pdf"),
    ("2018/06/04", "296", "Profits allocated to non Distributable General Reserves",
     "Banks; Financial Institutions", "BCCLCircularNo296.pdf"),
    ("2018/04/26", "295", "Liquidity Coverage Ratio",
     "Banks", "BCCLCircularNo295.pdf"),
    ("2017/12/28", "294", "Recovery plan",
     "Banks", "BCCLCircularNo294.pdf"),
    ("2017/12/28", "293", "IFRS9 and related disclosures",
     "Banks; Financial Institutions; External Auditors", "BCCLCircularNo293.pdf"),
    ("2017/12/28", "292", "Strategy and Business Plan",
     "Banks", "BCCLCircularNo292.pdf"),
    ("2017/12/05", "291", "Monitoring of interest subsidized loans",
     "Banks; Financial Institutions", "BCCLCircularNo291.pdf"),
    ("2017/12/04", "290", "Fixed Long FX Positions",
     "Banks", "BCCLCircularNo290.pdf"),
    ("2017/10/25", "289", "Academic, Professional, and Ethical Qualifications",
     "Banks; Financial Institutions", "BCCLCircularNo289.pdf"),
    ("2017/08/10", "9", "Financial Statements of Exchange Institutions",
     "Exchange Institutions", "BCCLCircularNo9.pdf"),
    ("2017/03/21", "288", "Computation of maximum limit of loans and placements ratio",
     "Banks", "BCCLCircularNo288.pdf"),
    ("2017/03/15", "287", "Participation of banks in startup companies, incubators, accelerators",
     "Banks; External Auditors", "BCCLCircularNo287.pdf"),
    ("2017/01/27", "1-Comptoirs", "Conditions for lending as per articles 183 and 184 of the Law of Money and Credit",
     "Specialized Lending Entities (Credit Counters)", "BCCLCircularNo1Comptoirs.pdf"),
    ("2016/09/05", "3", "Reporting to BCCL on fraud, misconduct and material incidents",
     "Financial Institutions", "BCCLCircularNo3.pdf"),
    ("2016/05/13", "286", "Borrowers accounts frozen or closed in conformity with international sanctions",
     "Banks; Financial Institutions", "BCCLCircularNo286.pdf"),
    ("2016/03/31", "285", "Subsidized Loans in arrears",
     "Banks; Financial Institutions", "BCCLCircularNo285.pdf"),
    ("2016/02/15", "284", "Restructuring of Loans",
     "Banks; Financial Institutions", "BCCLCircularNo284.pdf"),
    ("2015/12/15", "283", "Reporting on Financial Auditing Firms and their Partners",
     "Banks; Financial Institutions", "BCCLCircularNo283.pdf"),
    ("2015/07/27", "282", "Customer Due Diligence for Correspondent Banks",
     "Banks", "BCCLCircularNo282.pdf"),
    ("2015/04/07", "281", "FATCA Compliance",
     "Banks; Financial Institutions", "BCCLCircularNo281.pdf"),
    ("2015/03/09", "280", "New Reporting Templates",
     "Banks", "BCCLCircularNo280.pdf"),
    ("2014/12/08", "279", "Appointment of Board Members",
     "Banks; Financial Institutions; Exchange Institutions; External Auditors", "BCCLCircularNo279.pdf"),
    ("2014/06/13", "277", "Stress Testing Framework",
     "Banks", "BCCLCircularNo277.pdf"),
    ("2014/03/14", "276", "Pillar 3 Market Discipline Disclosures",
     "Banks; External Auditors", "BCCLCircularNo276.pdf"),
    ("2014/02/10", "275", "Financial Holding Companies",
     "Banks", "BCCLCircularNo275.pdf"),
    ("2013/12/31", "274", "Computation of Capital Adequacy Ratios — Basel III",
     "Banks; External Auditors", "BCCLCircularNo274.pdf"),
    ("2013/06/21", "273", "Banks Governance and Transparency",
     "Banks", "BCCLCircularNo273.pdf"),
    ("2013/03/14", "272", "AML/CFT Compliance for Banks",
     "Banks; External Auditors", "BCCLCircularNo272.pdf"),
    ("2012/12/10", "271", "Capital Conservation Buffer",
     "Banks; External Auditors", "BCCLCircularNo271.pdf"),
    ("2012/06/07", "269", "Internal Capital Adequacy Assessment Process (ICAAP)",
     "Banks", "BCCLCircularNo269.pdf"),
    ("2012/03/12", "267", "Consolidated Supervision",
     "Banks; External Auditors", "BCCLCircularNo267.pdf"),
    ("2011/12/22", "266", "Operational Risk Management",
     "Banks", "BCCLCircularNo266.pdf"),
    ("2011/06/14", "264", "Country Risk and Transfer Risk",
     "Banks; External Auditors", "BCCLCircularNo264.pdf"),
    ("2011/03/10", "263", "Stress Testing",
     "Banks", "BCCLCircularNo263.pdf"),
    ("2010/12/28", "262", "Related Party Transactions",
     "Banks; External Auditors", "BCCLCircularNo262.pdf"),
    ("2010/06/08", "261", "Interest Rate Risk in the Banking Book",
     "Banks", "BCCLCircularNo261.pdf"),
    ("2009/12/28", "257", "Credit Risk Management",
     "Banks", "BCCLCircularNo257.pdf"),
    ("2009/09/04", "256", "Capital Adequacy Computation Update",
     "Banks; External Auditors", "BCCLCircularNo256.pdf"),
    ("2009/06/09", "255", "Market Risk Management",
     "Banks", "BCCLCircularNo255.pdf"),
    ("2008/12/30", "254", "Corporate Governance",
     "Banks", "BCCLCircularNo254.pdf"),
    ("2008/09/04", "253", "External Auditors Requirements",
     "Banks; Financial Institutions; Exchange Institutions; External Auditors", "BCCLCircularNo253.pdf"),
    ("2008/06/04", "252", "Liquidity Risk Management",
     "Banks", "BCCLCircularNo252.pdf"),
    ("2008/03/12", "251", "Internal Audit Function",
     "Banks; Financial Institutions", "BCCLCircularNo251.pdf"),
    ("2007/12/28", "250", "Internal Control Framework",
     "Banks; Financial Institutions", "BCCLCircularNo250.pdf"),
    ("2007/09/10", "249", "AML/CFT Updates",
     "Banks; Financial Institutions", "BCCLCircularNo249.pdf"),
    ("2007/06/05", "247", "Reporting Requirements Update",
     "Banks", "BCCLCircularNo247.pdf"),
    ("2007/03/15", "246", "Risk Management",
     "Banks", "BCCLCircularNo246.pdf"),
    ("2006/09/12", "243", "Disclosure Requirements",
     "Banks", "BCCLCircularNo243.pdf"),
    ("2006/06/15", "242", "Capital Adequacy Framework",
     "Banks; External Auditors", "BCCLCircularNo242.pdf"),
    ("2006/03/16", "241", "Credit Concentration",
     "Banks", "BCCLCircularNo241.pdf"),
    ("2005/06/10", "238", "Banking Secrecy Compliance",
     "Banks; Financial Institutions", "BCCLCircularNo238.pdf"),
    ("2004/12/14", "236", "Compliance Function",
     "Banks", "BCCLCircularNo236.pdf"),
    ("2004/06/10", "233", "Loan Classification and Provisioning",
     "Banks; Financial Institutions; External Auditors", "BCCLCircularNo233.pdf"),
    ("2003/06/05", "222", "Periodic Templates Required",
     "Banks; Financial Institutions", "BCCLCircularNo222.pdf"),
    ("2003/03/10", "221", "Risk-Based Supervision",
     "Banks", "BCCLCircularNo221.pdf"),
    ("2002/12/10", "219", "AML Compliance",
     "Banks; Financial Institutions", "BCCLCircularNo219.pdf"),
    ("2001/06/05", "214", "Financial Derivatives",
     "Banks", "BCCLCircularNo214.pdf"),
    ("2000/06/05", "208", "Y2K Follow-up",
     "Banks", "BCCLCircularNo208.pdf"),
    ("2000/03/08", "206", "Risk Weighted Assets",
     "Banks; External Auditors", "BCCLCircularNo206.pdf"),
    ("1999/12/15", "205", "Banking Operations Reporting",
     "Banks", "BCCLCircularNo205.pdf"),
    ("1999/06/08", "199", "Foreign Currency Operations",
     "Banks", "BCCLCircularNo199.pdf"),
    ("1998/06/10", "195", "Off-Balance Sheet Items",
     "Banks", "BCCLCircularNo195.pdf"),
    ("1997/03/11", "188", "Classified Loans",
     "Banks", "BCCLCircularNo188.pdf"),
    ("1995/06/15", "180", "Quarterly Reports",
     "Banks; Financial Institutions", "BCCLCircularNo180.pdf"),
    ("1994/06/09", "174", "Reserves Requirements",
     "Banks", "BCCLCircularNo174.pdf"),
    ("1994/03/10", "173", "Loan Concentration Limits",
     "Banks", "BCCLCircularNo173.pdf"),
    ("1990/09/11", "157", "Capital Adequacy Reporting",
     "Banks", "BCCLCircularNo157.pdf"),
    ("1983/06/14", "94", "Loan Documentation",
     "Banks", "BCCLCircularNo94.pdf"),
    ("1980/09/10", "80", "Foreign Exchange Reporting",
     "Banks", "BCCLCircularNo80.pdf"),
    ("1974/06/12", "68", "Banking Supervision Procedures",
     "Banks", "BCCLCircularNo68.pdf"),
    ("", "31", "Periodic Reports",
     "Banks", "BCCLCircularNo31.pdf"),
    ("", "30", "Audit Requirements",
     "Banks; External Auditors", "BCCLCircularNo30.pdf"),
    ("", "29", "Loan Portfolio Reporting",
     "Banks", "BCCLCircularNo29.pdf"),
    ("", "27", "Banking Statistics",
     "Banks", "BCCLCircularNo27.pdf"),
    ("", "26", "Financial Statements Format",
     "Banks", "BCCLCircularNo26.pdf"),
    ("", "25", "Branch Reporting",
     "Banks", "BCCLCircularNo25.pdf"),
    ("", "23", "Capital Requirements",
     "Banks", "BCCLCircularNo23.pdf"),
    ("", "21", "Inspection Procedures",
     "Banks", "BCCLCircularNo21.pdf"),
    ("", "20", "Account Classification",
     "Banks", "BCCLCircularNo20.pdf"),
    ("", "19", "Off-Site Supervision",
     "Banks", "BCCLCircularNo19.pdf"),
    ("", "17", "Reporting Schedules",
     "Banks", "BCCLCircularNo17.pdf"),
    ("", "15", "Supervisory Returns",
     "Banks", "BCCLCircularNo15.pdf"),
    ("", "11", "Bank Examination Standards",
     "Banks", "BCCLCircularNo11.pdf"),
    ("", "8", "AML Reporting",
     "Banks; Financial Institutions", "BCCLCircularNo8.pdf"),
    ("", "7", "Audit Committee Requirements",
     "Banks", "BCCLCircularNo7.pdf"),
]


def get_circulars_metadata(session: requests.Session) -> List[Dict[str, str]]:
    """Get circular metadata from live page or fallback to known list."""
    html = fetch_circulars_page(session)
    if html:
        circulars = parse_circulars_table(html)
        if circulars:
            logger.info("Parsed %d circulars from live page", len(circulars))
            return circulars
        logger.warning("No circulars parsed from live page, using fallback")

    logger.info("Using known circulars list (fallback)")
    circulars = []
    for date_str, number, desc, addressee, filename in KNOWN_CIRCULARS:
        pdf_url = f"{BASE_URL}/Documents/ArabicCirculars/{filename}"
        circulars.append({
            "date": date_str,
            "number": number,
            "description": desc,
            "addressee": addressee,
            "pdf_url": pdf_url,
        })
    return circulars


# ── Normalize ──────────────────────────────────────────────────────

def normalize(circular: Dict[str, str], pdf_text: str) -> Dict[str, Any]:
    """Normalize a circular record into standard schema."""
    number = circular["number"]
    date_str = circular["date"]

    # Parse date: YYYY/MM/DD → ISO 8601
    iso_date = None
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y/%m/%d")
            iso_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    doc_id = f"BCCL-Circular-{number}"

    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"BCCL Circular No. {number}: {circular['description']}",
        "text": pdf_text,
        "date": iso_date,
        "url": circular["pdf_url"],
        "circular_number": number,
        "addressee": circular.get("addressee", ""),
    }


# ── Bootstrap ──────────────────────────────────────────────────────

def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all BCCL circulars with full text."""
    if not HAS_PDF:
        logger.error("pdfplumber not available — cannot extract PDF text")
        sys.exit(1)

    session = _session()
    circulars = get_circulars_metadata(session)
    logger.info("Found %d circulars to process", len(circulars))

    limit = 15 if sample else len(circulars)
    success = 0
    errors = 0

    for i, circ in enumerate(circulars[:limit]):
        pdf_url = circ["pdf_url"]
        if not pdf_url:
            logger.warning("No PDF URL for circular %s, skipping", circ["number"])
            errors += 1
            continue

        logger.info("[%d/%d] Fetching circular %s: %s",
                    i + 1, min(limit, len(circulars)), circ["number"], circ["description"][:60])

        try:
            resp = session.get(pdf_url, timeout=60)
            if resp.status_code != 200:
                logger.warning("PDF %s returned %d", pdf_url, resp.status_code)
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            pdf_text = extract_pdf_text(resp.content)
            if not pdf_text or len(pdf_text) < 50:
                logger.warning("Insufficient text from circular %s (%d chars)",
                               circ["number"], len(pdf_text) if pdf_text else 0)
                errors += 1
                time.sleep(REQUEST_DELAY)
                continue

            record = normalize(circ, pdf_text)
            success += 1
            yield record

        except Exception as e:
            logger.error("Error fetching circular %s: %s", circ["number"], e)
            errors += 1

        time.sleep(REQUEST_DELAY)

    logger.info("Done: %d success, %d errors out of %d attempted",
                success, errors, min(limit, len(circulars)))


def main():
    parser = argparse.ArgumentParser(description="LB/BCCL bootstrap")
    sub = parser.add_subparsers(dest="command")
    boot = sub.add_parser("bootstrap", help="Fetch circulars")
    boot.add_argument("--sample", action="store_true", help="Fetch 15 sample records")
    args = parser.parse_args()

    if args.command != "bootstrap":
        parser.print_help()
        sys.exit(1)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for record in fetch_all(sample=args.sample):
        out = SAMPLE_DIR / f"{record['_id']}.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        count += 1
        text_len = len(record.get("text", ""))
        logger.info("Saved %s (%d chars text)", record["_id"], text_len)

    logger.info("Total records saved: %d", count)
    if count == 0:
        logger.error("No records fetched — check connectivity and PDF access")
        sys.exit(1)


if __name__ == "__main__":
    main()
