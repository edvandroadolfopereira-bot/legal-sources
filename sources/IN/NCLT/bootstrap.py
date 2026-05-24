#!/usr/bin/env python3
"""
IN/NCLT -- National Company Law Tribunal

Fetches NCLT insolvency and corporate resolution orders from IBBI's
aggregation portal at ibbi.gov.in/orders/nclt.

Strategy:
  - Paginate through ibbi.gov.in/orders/nclt?page=N (1531+ pages, 20/page)
  - Parse HTML table rows for date, case title, case number, order type
  - Download order PDFs from /uploads/order/{hash}.pdf
  - Extract full text using pdfplumber
  - Normalize into standard schema

Data:
  - ~30,000+ orders from 2017–present
  - Covers insolvency admissions, liquidation, resolution plans,
    dissolution, and related IBC proceedings across all NCLT benches
  - PDFs are digital (text-extractable)
  - No authentication required

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py update             # Fetch orders from last 90 days
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.IN.NCLT")

BASE_URL = "https://ibbi.gov.in/orders/nclt"

# Bench code → full name mapping (from case number abbreviations)
BENCH_CODES = {
    "MB": "Mumbai", "MAH": "Mumbai", "MUM": "Mumbai",
    "ND": "New Delhi", "PB": "New Delhi",
    "CHE": "Chennai", "CHN": "Chennai",
    "AHM": "Ahmedabad",
    "ALH": "Allahabad", "ALL": "Allahabad",
    "AMR": "Amravati", "AMA": "Amravati",
    "BLR": "Bengaluru", "BNG": "Bengaluru", "BB": "Bengaluru", "KAR": "Bengaluru",
    "CHD": "Chandigarh", "CHND": "Chandigarh",
    "CTK": "Cuttack",
    "GUW": "Guwahati",
    "HYD": "Hyderabad",
    "IND": "Indore",
    "JPR": "Jaipur",
    "KOB": "Kochi", "KOC": "Kochi",
    "KOL": "Kolkata", "CAL": "Kolkata",
}


class NCLTScraper:
    """Scraper for IN/NCLT -- National Company Law Tribunal orders via IBBI."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research)",
            "Accept": "text/html, */*",
        })

    def _parse_page(self, page: int) -> list:
        """Fetch and parse a single page of NCLT orders from IBBI."""
        url = f"{BASE_URL}?page={page}"
        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to fetch page %d: %s", page, e)
            return []

        html = resp.text
        entries = []

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        for row in rows:
            # Extract PDF URL from onclick handler
            pdf_match = re.search(r"onclick=\"[^\"]*?'([^']+\.pdf)'", row)
            if not pdf_match:
                continue

            pdf_path = pdf_match.group(1)
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) < 4:
                continue

            serial = re.sub(r"<[^>]+>", "", cells[0]).strip()
            date_str = re.sub(r"<[^>]+>", "", cells[1]).strip()
            title_raw = re.sub(r"<[^>]+>", "", cells[2]).strip()
            order_type = re.sub(r"<[^>]+>", "", cells[3]).strip()

            # Clean up title — remove file size, &nbsp;, extra whitespace
            title_raw = re.sub(r"\s*\(\d+[\d.]*\s*[KMG]B\)", "", title_raw, flags=re.I)
            title_raw = title_raw.replace("&nbsp;", " ").replace("\xa0", " ")
            title_raw = re.sub(r"\s+", " ", title_raw).strip()

            # Extract case number from title
            case_no_match = re.search(r"\[([^\]]+)\]", title_raw)
            case_no = case_no_match.group(1).strip() if case_no_match else ""

            # Extract company name (before the bracket)
            company = re.sub(r"\[.*?\]", "", title_raw).strip()
            company = re.sub(r"^In the matter of\s+", "", company, flags=re.I).strip()

            # Detect bench from case number
            bench = self._detect_bench(case_no)

            entries.append({
                "serial": serial,
                "date_str": date_str,
                "title": title_raw,
                "company": company,
                "case_no": case_no,
                "order_type": order_type,
                "bench": bench,
                "pdf_path": pdf_path,
                "page": page,
            })

        logger.info("Page %d: %d entries", page, len(entries))
        return entries

    def _detect_bench(self, case_no: str) -> str:
        """Detect NCLT bench from case number abbreviation."""
        if not case_no:
            return ""
        # Patterns like (MB), (CHE), (ND), /AHM/, -MAH-
        m = re.search(r"[(/]([A-Z]{2,4})[)/]", case_no)
        if m:
            code = m.group(1)
            if code in BENCH_CODES:
                return BENCH_CODES[code]
        # Pattern like NCLT-MAH-2016
        m2 = re.search(r"NCLT[- ]([A-Z]{2,4})", case_no)
        if m2:
            code = m2.group(1)
            if code in BENCH_CODES:
                return BENCH_CODES[code]
        return ""

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse 'DD Mon, YYYY' format to ISO 8601."""
        if not date_str:
            return None
        for fmt in ("%d %b, %Y", "%d %B, %Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _download_pdf_text(self, pdf_path: str, doc_id: str) -> Optional[str]:
        """Download order PDF and extract text."""
        pdf_url = f"https://ibbi.gov.in{pdf_path}"

        # Try common.pdf_extract first
        try:
            text = extract_pdf_markdown(
                source="IN/NCLT",
                source_id=doc_id,
                pdf_url=pdf_url,
                table="case_law",
            )
            if text and len(text.strip()) > 100:
                return text.strip()
        except Exception:
            pass

        # Fallback: direct download + pdfplumber
        try:
            import pdfplumber
            resp = self.session.get(pdf_url, timeout=120)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and len(resp.content) < 1000:
                logger.warning("Non-PDF response for %s: %s", doc_id, content_type)
                return None

            if len(resp.content) == 0:
                return None

            text_parts = []
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)
            if len(full_text.strip()) > 100:
                return full_text.strip()
        except Exception as e:
            logger.warning("PDF extraction failed for %s: %s", doc_id, e)

        return None

    def _get_total_pages(self) -> int:
        """Detect total pages from the last page link."""
        try:
            resp = self.session.get(BASE_URL, timeout=30)
            resp.raise_for_status()
            pages = re.findall(r'page=(\d+)', resp.text)
            if pages:
                return max(int(p) for p in pages)
        except Exception as e:
            logger.error("Failed to detect total pages: %s", e)
        return 1531  # fallback

    def fetch_all(self) -> Generator:
        """Yield all NCLT order entries across all pages."""
        total_pages = self._get_total_pages()
        logger.info("Total pages to process: %d", total_pages)

        for page in range(1, total_pages + 1):
            entries = self._parse_page(page)
            for entry in entries:
                yield entry
            time.sleep(1.5)

    def fetch_updates(self, since: datetime) -> Generator:
        """Yield recent orders (page through until we pass the since date)."""
        for page in range(1, 200):
            entries = self._parse_page(page)
            if not entries:
                break

            all_old = True
            for entry in entries:
                iso_date = self._parse_date(entry["date_str"])
                if iso_date:
                    entry_dt = datetime.strptime(iso_date, "%Y-%m-%d")
                    if entry_dt >= since.replace(tzinfo=None):
                        all_old = False
                        yield entry
                    else:
                        continue
                else:
                    yield entry
                    all_old = False

            if all_old:
                logger.info("All entries on page %d are older than %s, stopping",
                            page, since.isoformat())
                break
            time.sleep(1.5)

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw entry into standard schema."""
        case_no = raw.get("case_no", "")
        pdf_path = raw.get("pdf_path", "")
        date_str = raw.get("date_str", "")
        company = raw.get("company", "")
        order_type = raw.get("order_type", "")

        # Build unique ID from PDF hash
        pdf_hash = re.search(r"/([a-f0-9]{20,})\.pdf", pdf_path)
        if pdf_hash:
            doc_id = f"NCLT-{pdf_hash.group(1)[:16]}"
        elif case_no:
            safe_case = re.sub(r"[^A-Za-z0-9]", "-", case_no)[:40]
            doc_id = f"NCLT-{safe_case}"
        else:
            doc_id = f"NCLT-{raw.get('serial', 'unknown')}-p{raw.get('page', 0)}"

        # Download and extract PDF text
        text = self._download_pdf_text(pdf_path, doc_id)
        if not text:
            logger.warning("No text extracted for %s (%s)", doc_id, case_no)
            return None

        decision_date = self._parse_date(date_str)

        # Build title
        title = raw.get("title", "")
        if not title and company:
            title = f"In the matter of {company}"
            if case_no:
                title += f" [{case_no}]"

        return {
            "_id": doc_id,
            "_source": "IN/NCLT",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": decision_date,
            "url": f"https://ibbi.gov.in{pdf_path}",
            "case_no": case_no,
            "company": company,
            "order_type": order_type,
            "bench": raw.get("bench", ""),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IN/NCLT bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Full initial pull")
    boot.add_argument("--sample", action="store_true", help="Fetch only 15 sample records")

    upd = sub.add_parser("update", help="Fetch recent orders")
    upd.add_argument("--days", type=int, default=90, help="Look back N days (default 90)")

    sub.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()
    scraper = NCLTScraper()

    if args.command == "test":
        logger.info("Testing NCLT/IBBI connectivity...")
        entries = scraper._parse_page(1)
        logger.info("Page 1: %d entries", len(entries))
        if entries:
            sample = entries[0]
            logger.info("Sample: case=%s, date=%s, type=%s",
                        sample["case_no"], sample["date_str"], sample["order_type"])
        total = scraper._get_total_pages()
        logger.info("Total pages: %d (approx %d orders)", total, total * 20)
        logger.info("Test PASSED")

    elif args.command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        limit = 15 if args.sample else 999999

        for raw in scraper.fetch_all():
            rec = scraper.normalize(raw)
            if rec:
                count += 1
                out_path = sample_dir / f"{rec['_id']}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
                logger.info("[%d] Saved %s (%d chars text)", count, rec["_id"],
                            len(rec.get("text", "")))
                if count >= limit:
                    break

        logger.info("Bootstrap complete: %d records saved to %s", count, sample_dir)

    elif args.command == "update":
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0

        for raw in scraper.fetch_updates(since):
            rec = scraper.normalize(raw)
            if rec:
                count += 1
                out_path = sample_dir / f"{rec['_id']}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
                logger.info("[%d] Saved %s", count, rec["_id"])

        logger.info("Update complete: %d records saved", count)

    else:
        parser.print_help()
