"""
Legal Data Hunter - Bulgarian Commission for Protection of Competition (CPC) Scraper

Fetches decisions, determinations, and orders from the public electronic registry
of the Bulgarian Commission for Protection of Competition (Комисия за защита на
конкуренцията / КЗК).

Data source: https://reg.cpc.bg/
Method: ASP.NET WebForms HTML scraping + PDF extraction via __doPostBack
Coverage: 2008-present, three legal frameworks (Competition, Public Procurement, Concessions)
"""

import io
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Tuple
from html import unescape

import requests
from bs4 import BeautifulSoup

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("BG/CPC")

BASE_URL = "https://reg.cpc.bg"

# Law types (dt parameter)
LAW_TYPES = {
    1: "ЗЗК",   # Competition Protection Law
    2: "ЗОП",   # Public Procurement Law
    3: "ЗК",    # Concessions Law
}

# Document types (ot parameter) — only for AllResolutions
DOC_TYPES = {
    2: "decision",        # Решения
    6: "determination",   # Определения
    7: "order",           # Разпореждания
}

# Year postback control indices (2026 -> ctl00, 2025 -> ctl01, etc.)
# Years go from 2026 down to 2008, ctl00 through ctl18
YEAR_RANGE = list(range(2026, 2007, -1))  # 2026..2008


class BulgarianCPCScraper(BaseScraper):
    """
    Scraper for: Bulgarian Commission for Protection of Competition (КЗК)
    Country: BG
    URL: https://reg.cpc.bg/

    Data types: case_law (competition decisions, procurement review, concession disputes)
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "bg,en;q=0.5",
        })

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions/determinations/orders across all law types and years."""
        for dt, law_name in LAW_TYPES.items():
            for ot, doc_type in DOC_TYPES.items():
                logger.info(f"Fetching {doc_type}s under {law_name} (dt={dt}, ot={ot})")
                yield from self._fetch_resolutions(dt, ot, doc_type, law_name)

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield documents modified since a given date (fetch current year only)."""
        current_year = datetime.now().year
        for dt, law_name in LAW_TYPES.items():
            for ot, doc_type in DOC_TYPES.items():
                logger.info(f"Fetching recent {doc_type}s under {law_name}")
                yield from self._fetch_resolutions(
                    dt, ot, doc_type, law_name, years=[current_year], since=since
                )

    def _fetch_resolutions(
        self,
        dt: int,
        ot: int,
        doc_type: str,
        law_name: str,
        years: Optional[List[int]] = None,
        since: Optional[datetime] = None,
    ) -> Generator[dict, None, None]:
        """
        Fetch all resolutions for a given law type and document type.
        Iterates through years and pages.
        """
        listing_url = f"{BASE_URL}/AllResolutions.aspx?dt={dt}&ot={ot}"

        # Initial GET to establish session and get first page
        self.rate_limiter.wait()
        try:
            resp = self.session.get(listing_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to load listing page dt={dt} ot={ot}: {e}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")

        # Determine which years to process
        target_years = years if years else YEAR_RANGE

        for year_idx, year in enumerate(target_years):
            # If not the default year (first load = current year), postback to switch
            if year_idx > 0 or (years and year != YEAR_RANGE[0]):
                ctl_idx = YEAR_RANGE.index(year) if year in YEAR_RANGE else None
                if ctl_idx is None:
                    continue
                ctl_id = f"ctl00$cntPlaceHldMain$dlYears$ctl{ctl_idx:02d}$lnkYear"
                soup = self._do_postback(listing_url, soup, ctl_id)
                if soup is None:
                    logger.warning(f"Failed to switch to year {year}")
                    continue

            # Now iterate through pages for this year
            page_num = 1
            while True:
                # Extract dossier IDs and metadata from current page
                doss_ids = self._extract_dossier_ids(soup)
                if not doss_ids:
                    break

                logger.info(f"  {law_name} {doc_type} {year} page {page_num}: {len(doss_ids)} entries")

                for doss_id, meta in doss_ids:
                    # Date filter for updates
                    if since and meta.get("date"):
                        try:
                            doc_date = datetime.strptime(meta["date"], "%Y-%m-%d")
                            doc_date = doc_date.replace(tzinfo=timezone.utc)
                            if doc_date < since:
                                continue
                        except Exception:
                            pass

                    raw = self._fetch_dossier_with_pdf(doss_id, meta, doc_type, law_name, dt)
                    if raw:
                        yield raw

                # Try next page
                next_btn = soup.find("a", id=re.compile(r"lnkButtonNext"))
                if not next_btn or "disabled" in next_btn.get("class", []):
                    break

                href = next_btn.get("href", "")
                target_match = re.search(r"doPostBack\('([^']+)'", href)
                if not target_match:
                    break

                soup = self._do_postback(listing_url, soup, target_match.group(1))
                if soup is None:
                    break
                page_num += 1

                if page_num > 200:
                    logger.warning(f"Page safety limit reached for {law_name} {doc_type} {year}")
                    break

    def _extract_dossier_ids(self, soup: BeautifulSoup) -> List[Tuple[str, dict]]:
        """Extract dossier IDs and basic metadata from a listing page."""
        results = []
        # Find all links to Dossier.aspx?DossID=
        doss_links = soup.find_all("a", href=re.compile(r"Dossier\.aspx\?DossID=\d+"))
        seen = set()
        for link in doss_links:
            href = link.get("href", "")
            match = re.search(r"DossID=(\d+)", href)
            if match:
                doss_id = match.group(1)
                if doss_id in seen:
                    continue
                seen.add(doss_id)

                # Try to extract metadata from the surrounding table
                meta = self._extract_listing_meta(link)
                results.append((doss_id, meta))

        return results

    def _extract_listing_meta(self, link_element) -> dict:
        """Extract metadata from the listing page table row."""
        meta = {}

        # Walk up to find the containing table/panel
        parent = link_element
        for _ in range(10):
            parent = parent.parent
            if parent is None:
                break
            text = parent.get_text(separator="\n", strip=True)
            if len(text) > 100:
                # Extract decision number
                act_match = re.search(r"(АКТ-\d+-[\d.]+\d{4})", text)
                if act_match:
                    meta["act_number"] = act_match.group(1)

                # Extract date
                date_match = re.search(r"Дата на решение:\s*([\d.]+)", text)
                if date_match:
                    try:
                        d = datetime.strptime(date_match.group(1).strip(" г."), "%d.%m.%Y")
                        meta["date"] = d.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                # Extract pronouncement text
                pron_match = re.search(r"Произнасяне:\s*(.+?)(?:\n|Правно|Номер|Вид)", text, re.DOTALL)
                if pron_match:
                    meta["pronouncement"] = pron_match.group(1).strip()

                # Extract subject
                subj_match = re.search(r"Предмет/подпредмет:\s*(.+?)(?:\n|$)", text)
                if subj_match:
                    meta["subject"] = subj_match.group(1).strip()

                # Extract parties
                init_match = re.search(r"Инициатор\(и\):\s*(.+?)(?:\n|$)", text)
                if init_match:
                    meta["initiator"] = init_match.group(1).strip()
                resp_match = re.search(r"Ответник\(ници\):\s*(.+?)(?:\n|$)", text)
                if resp_match:
                    meta["respondent"] = resp_match.group(1).strip()

                # Extract case number
                case_match = re.search(r"КЗК[/-](\d+/\d{4})", text)
                if case_match:
                    meta["case_number"] = f"КЗК/{case_match.group(1)}"

                break

        return meta

    def _fetch_dossier_with_pdf(
        self, doss_id: str, meta: dict, doc_type: str, law_name: str, dt: int
    ) -> Optional[dict]:
        """
        Fetch an individual dossier page and download the PDF for full text.
        """
        dossier_url = f"{BASE_URL}/Dossier.aspx?DossID={doss_id}"

        self.rate_limiter.wait()
        try:
            resp = self.session.get(dossier_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch dossier {doss_id}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract detailed metadata from the dossier page
        dossier_meta = self._extract_dossier_meta(soup)
        meta.update({k: v for k, v in dossier_meta.items() if v and not meta.get(k)})

        # Find PDF download button(s)
        pdf_links = soup.find_all("a", id=re.compile(r"linkBtnPDF"))
        full_text = ""

        if pdf_links:
            # Download the first PDF (primary decision document)
            pdf_target = pdf_links[0].get("href", "")
            target_match = re.search(r"doPostBack\('([^']+)'", pdf_target)
            if target_match:
                full_text = self._download_and_extract_pdf(
                    dossier_url, soup, target_match.group(1)
                )

        if not full_text:
            # Fall back to pronouncement text if PDF extraction fails
            full_text = meta.get("pronouncement", "")
            if full_text:
                logger.info(f"Dossier {doss_id}: using pronouncement text (no PDF)")
            else:
                logger.warning(f"Dossier {doss_id}: no text found")
                return None

        title = meta.get("act_number", "") or dossier_meta.get("act_number", "")
        if not title:
            title = f"CPC {doc_type} DossID {doss_id}"

        return {
            "doss_id": doss_id,
            "title": title,
            "full_text": full_text,
            "date": meta.get("date"),
            "doc_type": doc_type,
            "law_type": law_name,
            "law_type_code": dt,
            "case_number": meta.get("case_number", ""),
            "subject": meta.get("subject", ""),
            "initiator": meta.get("initiator", ""),
            "respondent": meta.get("respondent", ""),
            "pronouncement": meta.get("pronouncement", ""),
            "url": dossier_url,
        }

    def _extract_dossier_meta(self, soup: BeautifulSoup) -> dict:
        """Extract metadata from an individual dossier page."""
        meta = {}
        text = soup.get_text(separator="\n", strip=True)

        # Case number
        case_match = re.search(r"(КЗК[/-]\d+/\d{4})", text)
        if case_match:
            meta["case_number"] = case_match.group(1)

        # Act number
        act_match = re.search(r"(АКТ-\d+-[\d.]+\d{4})", text)
        if act_match:
            meta["act_number"] = act_match.group(1)

        # Date
        date_match = re.search(r"Дата на решение.*?(\d{2}\.\d{2}\.\d{4})", text)
        if not date_match:
            date_match = re.search(r"Дата на определение.*?(\d{2}\.\d{2}\.\d{4})", text)
        if date_match:
            try:
                d = datetime.strptime(date_match.group(1), "%d.%m.%Y")
                meta["date"] = d.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Subject
        subj_match = re.search(r"Предмет/подпредмет:\s*(.+?)(?:\n|$)", text)
        if subj_match:
            meta["subject"] = subj_match.group(1).strip()

        return meta

    def _download_and_extract_pdf(
        self, page_url: str, soup: BeautifulSoup, event_target: str
    ) -> str:
        """Download a PDF via ASP.NET postback and extract text."""
        viewstate = soup.find("input", {"name": "__VIEWSTATE"})
        viewstate_gen = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})

        if not viewstate:
            logger.warning("No __VIEWSTATE found for PDF download")
            return ""

        data = {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate["value"],
        }
        if viewstate_gen:
            data["__VIEWSTATEGENERATOR"] = viewstate_gen["value"]

        event_val = soup.find("input", {"name": "__EVENTVALIDATION"})
        if event_val:
            data["__EVENTVALIDATION"] = event_val["value"]

        self.rate_limiter.wait()
        try:
            resp = self.session.post(page_url, data=data, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"PDF download failed: {e}")
            return ""

        # Check if response is actually a PDF
        content_type = resp.headers.get("Content-Type", "")
        is_pdf = (
            "pdf" in content_type.lower()
            or "octet-stream" in content_type.lower()
            or resp.content[:4] == b"%PDF"
        )

        if not is_pdf or len(resp.content) < 100:
            logger.warning(f"Response is not a PDF (Content-Type: {content_type}, size: {len(resp.content)})")
            return ""

        return self._extract_text_from_pdf(resp.content)

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            text = "\n\n".join(text_parts)

            # Clean up
            text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
            text = text.replace("\xa0", " ")
            text = text.strip()

            return text

        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return ""

    def _do_postback(
        self, page_url: str, soup: BeautifulSoup, event_target: str
    ) -> Optional[BeautifulSoup]:
        """Perform an ASP.NET __doPostBack and return the resulting page soup."""
        viewstate = soup.find("input", {"name": "__VIEWSTATE"})
        viewstate_gen = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})

        if not viewstate:
            logger.warning("No __VIEWSTATE found for postback")
            return None

        data = {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate["value"],
        }
        if viewstate_gen:
            data["__VIEWSTATEGENERATOR"] = viewstate_gen["value"]

        event_val = soup.find("input", {"name": "__EVENTVALIDATION"})
        if event_val:
            data["__EVENTVALIDATION"] = event_val["value"]

        self.rate_limiter.wait()
        try:
            resp = self.session.post(page_url, data=data, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"Postback failed for {event_target}: {e}")
            return None

    def normalize(self, raw: dict) -> dict:
        """Transform a raw document into the standard schema."""
        doss_id = raw.get("doss_id", "")
        doc_type = raw.get("doc_type", "decision")

        _id = f"BG/CPC/{doc_type}/{doss_id}"

        full_text = raw.get("full_text", "")

        # Build a descriptive title
        title = raw.get("title", "")
        if raw.get("subject"):
            title = f"{title} — {raw['subject']}"

        parties = []
        if raw.get("initiator"):
            parties.append(f"Initiator: {raw['initiator']}")
        if raw.get("respondent"):
            parties.append(f"Respondent: {raw['respondent']}")

        return {
            "_id": _id,
            "_source": "BG/CPC",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": full_text,
            "date": raw.get("date"),
            "url": raw.get("url"),
            "doss_id": doss_id,
            "doc_type": doc_type,
            "law_type": raw.get("law_type", ""),
            "case_number": raw.get("case_number", ""),
            "subject": raw.get("subject", ""),
            "parties": parties,
            "pronouncement": raw.get("pronouncement", ""),
        }


# -- CLI Entry Point -----------------------------------------------

def main():
    scraper = BulgarianCPCScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update] [--sample] [--sample-size N]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 12
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command == "bootstrap":
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
            print(f"\nSample complete: {stats.get('sample_records_saved', 0)} records saved to sample/")
        else:
            stats = scraper.bootstrap()
            print(f"\nBootstrap complete: {stats['records_new']} new, {stats['records_updated']} updated, {stats['records_skipped']} skipped")
    elif command == "update":
        stats = scraper.update()
        print(f"\nUpdate complete: {stats['records_new']} new, {stats['records_updated']} updated")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
