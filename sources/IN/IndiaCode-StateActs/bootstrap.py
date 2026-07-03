#!/usr/bin/env python3
"""
IN/IndiaCode-StateActs — India Code Digital Repository of STATE Acts

Fetches Indian *state and union-territory* legislation (acts) with full text
from indiacode.nic.in. Complements IN/IndiaCode (which covers Central Acts only).

IndiaCode is a DSpace repository. Under the "State Act" community
(handle 123456789/2180) each state / UT has its own collection. This scraper
iterates every state collection, browses its acts, and extracts full text.

Full-text strategy (per act):
  1. Some acts expose section-level HTML via the SectionPageContent AJAX
     endpoint (same as Central Acts) — preferred when present.
  2. Most state acts attach the act as a PDF bitstream
     (/bitstream/123456789/{handle}/N/{file}.pdf) — extracted via the project's
     multi-backend common.pdf_extract helper (the English "(e)" PDF is preferred).

Data:
  - ~35 states / union territories, tens of thousands of acts total
  - Full text per act (HTML sections or extracted PDF)
  - Metadata: act number, year, enactment/enforcement date, department, state

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records (cross-state)
  python bootstrap.py update             # Fetch recently enacted acts
  python bootstrap.py test               # Quick connectivity test
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.IN.IndiaCode-StateActs")

SOURCE_ID = "IN/IndiaCode-StateActs"
BASE_URL = "https://www.indiacode.nic.in"
SECTION_API = f"{BASE_URL}/SectionPageContent"

# State / UT collection handles under the "State Act" community (123456789/2180),
# mapped to ISO 3166-2:IN codes. Discovered from the live community listing.
# handle: (state_name, iso_3166_2_code)
STATE_COLLECTIONS: Dict[str, Tuple[str, str]] = {
    "2454": ("Andaman and Nicobar Islands", "IN-AN"),
    "2486": ("Andhra Pradesh", "IN-AP"),
    "2487": ("Arunachal Pradesh", "IN-AR"),
    "2513": ("Assam", "IN-AS"),
    "2488": ("Bihar", "IN-BR"),
    "2489": ("Chandigarh", "IN-CH"),
    "2490": ("Chhattisgarh", "IN-CT"),
    "2492": ("Dadra and Nagar Haveli and Daman and Diu", "IN-DH"),
    "2493": ("Delhi", "IN-DL"),
    "2514": ("Goa", "IN-GA"),
    "2455": ("Gujarat", "IN-GJ"),
    "2193": ("Haryana", "IN-HR"),
    "2494": ("Himachal Pradesh", "IN-HP"),
    "2495": ("Jammu and Kashmir", "IN-JK"),
    "2515": ("Jharkhand", "IN-JH"),
    "2485": ("Karnataka", "IN-KA"),
    "2516": ("Kerala", "IN-KL"),
    "14011": ("Ladakh", "IN-LA"),
    "2496": ("Lakshadweep", "IN-LD"),
    "2497": ("Madhya Pradesh", "IN-MP"),
    "2517": ("Maharashtra", "IN-MH"),
    "2498": ("Manipur", "IN-MN"),
    "2499": ("Meghalaya", "IN-ML"),
    "2500": ("Mizoram", "IN-MZ"),
    "2501": ("Nagaland", "IN-NL"),
    "2502": ("Odisha", "IN-OR"),
    "2503": ("Puducherry", "IN-PY"),
    "2504": ("Punjab", "IN-PB"),
    "2505": ("Rajasthan", "IN-RJ"),
    "2506": ("Sikkim", "IN-SK"),
    "2507": ("Tamil Nadu", "IN-TN"),
    "2508": ("Telangana", "IN-TG"),
    "2509": ("Tripura", "IN-TR"),
    "2511": ("Uttarakhand", "IN-UT"),
    "2510": ("Uttar Pradesh", "IN-UP"),
    "2512": ("West Bengal", "IN-WB"),
}


def clean_html(raw_html: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text.strip()


class IndiaCodeStateActsScraper(BaseScraper):
    """Scraper for IN/IndiaCode-StateActs — Indian state & UT legislation."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_request = 0.0

    def _rate_limited_get(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited GET request with retry."""
        elapsed = time.time() - self._last_request
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        self._last_request = time.time()

        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=40, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    raise
                logger.warning(f"Retry {attempt+1}/3 for {url}: {e}")
                time.sleep(5 * (attempt + 1))

    # ── Browse a single state collection ─────────────────────────────

    def _browse_state(self, handle: str) -> Generator[Dict, None, None]:
        """Iterate the paginated browse listing for one state collection."""
        offset = 0
        rpp = 100
        while True:
            url = (f"{BASE_URL}/handle/123456789/{handle}/browse"
                   f"?type=shorttitle&order=ASC&rpp={rpp}&offset={offset}")
            try:
                resp = self._rate_limited_get(url)
            except Exception as e:
                logger.warning(f"Browse failed for state handle {handle} offset={offset}: {e}")
                return
            soup = BeautifulSoup(resp.text, "html.parser")

            # Rows are 4 cells: enactment_date | act_number | short_title | view_link
            cells = soup.find_all("td", class_=re.compile(r"(even|odd)Row"))
            count = 0
            for i in range(0, len(cells), 4):
                if i + 3 >= len(cells):
                    break
                date_cell, number_cell, title_cell, view_cell = cells[i:i + 4]
                view_link = view_cell.find("a", href=True)
                if not view_link:
                    continue
                m = re.search(r"handle/123456789/(\d+)", view_link["href"])
                if not m:
                    continue
                yield {
                    "handle_id": m.group(1),
                    "title": title_cell.get_text(strip=True),
                    "act_number": number_cell.get_text(strip=True),
                    "enactment_date_raw": date_cell.get_text(strip=True),
                }
                count += 1

            if count == 0 or count < rpp:
                break
            offset += rpp

    # ── Round-robin across all states (cross-state ordering) ──────────

    def _iter_all_acts(self) -> Generator[Dict, None, None]:
        gens = []
        for handle, (name, code) in STATE_COLLECTIONS.items():
            gens.append((name, code, handle, self._browse_state(handle)))

        active = True
        while active:
            active = False
            for name, code, handle, gen in gens:
                try:
                    act = next(gen)
                except StopIteration:
                    continue
                active = True
                act["state_name"] = name
                act["state_code"] = code
                act["state_handle"] = handle
                yield act

    # ── Fetch act page: metadata + section links + PDF bitstream ──────

    def _fetch_act_page(self, handle_id: str) -> Optional[Dict]:
        url = f"{BASE_URL}/handle/123456789/{handle_id}?view_type=browse"
        resp = self._rate_limited_get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        metadata: Dict = {}
        for row in soup.find_all("tr"):
            label_cell = row.find("td", class_="metadataFieldLabel")
            value_cell = row.find("td", class_="metadataFieldValue")
            if label_cell and value_cell:
                label = label_cell.get_text(strip=True).rstrip(":").strip()
                value = value_cell.get_text(strip=True)
                if label == "Act Number":
                    metadata["act_number"] = value
                elif label == "Enactment Date":
                    metadata["enactment_date"] = value
                elif label == "Act Year":
                    metadata["act_year"] = value
                elif label == "Long Title":
                    metadata["long_title"] = value
                elif label == "Department":
                    metadata["department"] = value
                elif label == "Ministry":
                    metadata["ministry"] = value
                elif label == "Enforcement Date":
                    metadata["enforcement_date"] = value

        # Section-level HTML links (show-data?actid=...&sectionId=...)
        sections = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "show-data" not in href or "actid=" not in href:
                continue
            actid_m = re.search(r"actid=([^&§]+)", href)
            secid_m = re.search(r"(?:[sS]ection[iI]d|§ionId)=(\d+)", href)
            secno_m = re.search(r"(?:[sS]ection[nN]o|§ionno)=([^&§]+)", href)
            if actid_m and secid_m:
                sections.append({
                    "actid": actid_m.group(1),
                    "section_id": secid_m.group(1),
                    "section_no": secno_m.group(1) if secno_m else None,
                    "title": link.get_text(strip=True),
                })
        metadata["sections"] = sections

        # PDF bitstream attached to this act's own handle
        metadata["pdf_url"] = self._pick_pdf(soup, handle_id)
        return metadata

    @staticmethod
    def _pick_pdf(soup: BeautifulSoup, handle_id: str) -> Optional[str]:
        """Pick the best PDF bitstream for the act, preferring the English copy."""
        candidates: List[str] = []
        pat = re.compile(rf"/bitstream/123456789/{handle_id}/\d+/[^\"']+\.pdf", re.I)
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if pat.search(href):
                candidates.append(href)
        if not candidates:
            return None

        def score(h: str) -> int:
            low = h.lower()
            s = 0
            if "%28e%29" in low or "(e)" in low or "_e" in low or "eng" in low:
                s += 3
            if "%28h%29" in low or "(h)" in low or "hindi" in low or "_h" in low:
                s -= 3
            return s

        best = sorted(candidates, key=score, reverse=True)[0]
        if best.startswith("http"):
            return best
        return BASE_URL + best

    # ── Section full text via AJAX (when present) ────────────────────

    def _fetch_section_text(self, actid: str, section_id: str) -> Optional[str]:
        url = f"{SECTION_API}?actid={actid}&sectionID={section_id}"
        try:
            resp = self._rate_limited_get(url)
            data = resp.json()
            text = clean_html(data.get("content", ""))
            footnote = clean_html(data.get("footnote", ""))
            if footnote:
                text += "\n\n[Footnotes]\n" + footnote
            return text
        except Exception as e:
            logger.warning(f"Failed to fetch section {section_id}: {e}")
            return None

    def _fetch_sections_full_text(self, sections: List[Dict]) -> str:
        parts = []
        for sec in sections:
            sec_text = self._fetch_section_text(sec["actid"], sec["section_id"])
            if sec_text:
                header = f"Section {sec['section_no']}" if sec.get("section_no") else "Section"
                if sec.get("title"):
                    header += f". {sec['title']}"
                parts.append(f"--- {header} ---\n{sec_text}")
        return "\n\n".join(parts)

    # ── BaseScraper interface ────────────────────────────────────────

    def fetch_all(self) -> Generator[dict, None, None]:
        for act in self._iter_all_acts():
            handle_id = act["handle_id"]
            label = f"{act['state_code']} {act['title'][:50]}"
            try:
                page = self._fetch_act_page(handle_id)
            except Exception as e:
                logger.error(f"Act page error for {label}: {e}")
                continue
            if not page:
                continue

            full_text = ""
            text_source = None

            # 1) Section-level HTML, if available
            if page.get("sections"):
                full_text = self._fetch_sections_full_text(page["sections"])
                if full_text and len(full_text) >= 200:
                    text_source = "html_sections"
                else:
                    full_text = ""

            # 2) Fall back to PDF bitstream
            if not full_text and page.get("pdf_url"):
                try:
                    pdf_text = extract_pdf_markdown(
                        SOURCE_ID, handle_id,
                        pdf_url=page["pdf_url"], table="legislation", force=True,
                    )
                except Exception as e:
                    logger.warning(f"PDF extract failed for {label}: {e}")
                    pdf_text = None
                if pdf_text:
                    full_text = pdf_text
                    text_source = "pdf"

            if not full_text:
                logger.warning(f"No full text for {label} (handle={handle_id})")
                continue

            yield {
                "handle_id": handle_id,
                "title": act["title"],
                "act_number": act.get("act_number") or page.get("act_number"),
                "enactment_date_raw": act.get("enactment_date_raw"),
                "enactment_date": page.get("enactment_date"),
                "act_year": page.get("act_year"),
                "long_title": page.get("long_title"),
                "department": page.get("department"),
                "ministry": page.get("ministry"),
                "enforcement_date": page.get("enforcement_date"),
                "state_name": act["state_name"],
                "state_code": act["state_code"],
                "text_source": text_source,
                "text": full_text,
            }

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        for raw in self.fetch_all():
            date_str = raw.get("enactment_date")
            if not date_str:
                yield raw
                continue
            try:
                act_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if act_date >= since:
                    yield raw
            except ValueError:
                yield raw

    def normalize(self, raw: dict) -> Optional[dict]:
        text = raw.get("text", "")
        if not text or len(text) < 100:
            return None

        # Resolve ISO date
        date = raw.get("enactment_date")
        if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            date = None
        if not date and raw.get("enactment_date_raw"):
            try:
                date = datetime.strptime(raw["enactment_date_raw"], "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                date = None

        year = raw.get("act_year")
        if not year and date:
            year = date[:4]
        if not year:
            ym = re.search(r",\s*(\d{4})", raw.get("title", ""))
            if ym:
                year = ym.group(1)

        return {
            "_id": f"IN_IndiaCode_StateActs_{raw['state_code']}_{raw['handle_id']}",
            "_source": "IN/IndiaCode-StateActs",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", "").rstrip("."),
            "text": text,
            "date": date,
            "url": f"{BASE_URL}/handle/123456789/{raw['handle_id']}?view_type=browse",
            "act_number": raw.get("act_number"),
            "year": year,
            "long_title": raw.get("long_title"),
            "department": raw.get("department"),
            "enforcement_date": raw.get("enforcement_date"),
            "country": "IN",
            "jurisdiction": raw.get("state_name"),
            "jurisdiction_code": raw.get("state_code"),
            "text_source": raw.get("text_source"),
        }


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="IN/IndiaCode-StateActs data fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--sample-size", type=int, default=15)
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = IndiaCodeStateActsScraper()

    if args.command == "test":
        logger.info("Testing connectivity to India Code (state acts)...")
        n = 0
        for act in scraper._iter_all_acts():
            logger.info(f"  {act['state_code']} | {act['title'][:60]} (handle={act['handle_id']})")
            n += 1
            if n >= 5:
                break
        if n:
            page = scraper._fetch_act_page(act["handle_id"])
            logger.info(f"sections={len(page.get('sections', []))} pdf={bool(page.get('pdf_url'))}")
        logger.info("Test complete.")
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        stats = scraper.bootstrap(sample_mode=args.sample, sample_size=args.sample_size)
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")
    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
