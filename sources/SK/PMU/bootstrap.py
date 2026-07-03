#!/usr/bin/env python3
"""
SK/PMU -- Slovakia Antimonopoly Office (PMÚ SR) Decisions Fetcher

Fetches competition law decisions from the Antimonopoly Office of the
Slovak Republic. Covers cartels, abuse of dominance, concentrations,
vertical agreements, and other competition cases.

Strategy:
  - Scrape paginated decision list at /prehlad-rozhodnuti/?page=N
  - For each case, visit the detail page to collect metadata + PDF links
  - Download PDF decisions and extract full text via pdfplumber

Endpoints:
  - List: https://www.antimon.gov.sk/prehlad-rozhodnuti/?page={N}
  - Detail: https://www.antimon.gov.sk/{slug}/
  - PDFs: https://www.antimon.gov.sk/data/att/{hash}/{id}.{hash}.pdf

Data:
  - ~400+ decisions across 21+ pages (20 per page)
  - Each case may have multiple decisions (first instance + appeal)
  - Language: Slovak

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import io
import html as html_module
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from urllib.parse import urljoin

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient
from common.pdf_extract import extract_pdf_markdown

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SK.PMU")

BASE_URL = "https://www.antimon.gov.sk"
LIST_URL = "/prehlad-rozhodnuti/"


def _parse_sk_date(date_str: str) -> Optional[str]:
    """Parse Slovak date format DD.MM.YYYY to ISO 8601."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%d.%m.%Y", "%d. %m. %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class PMUScraper(BaseScraper):
    """Scraper for Slovakia Antimonopoly Office decisions."""

    def __init__(self, source_dir=None):
        # source_dir is optional so the VPS bootstrap-fast wrapper can do
        # PMUScraper() by introspection (issue #971); BaseScraper.__init__
        # resolves None to this module's directory.
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (legal research; +https://github.com/worldwidelaw/legal-sources)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sk,en;q=0.5",
            },
            timeout=60,
        )

    def _get_case_list_page(self, page: int) -> List[Dict[str, str]]:
        """Fetch one page of the decision list and return case summaries."""
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 required: pip install beautifulsoup4")

        self.rate_limiter.wait()
        resp = self.client.get(f"{LIST_URL}?page={page}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        cases = []
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            link = cells[0].find("a")
            if not link or not link.get("href"):
                continue
            cases.append({
                "participant": cells[0].get_text(strip=True),
                "detail_url": link["href"],
                "proceeding_type": cells[1].get_text(strip=True),
                "decision_date": cells[2].get_text(strip=True),
                "instance": cells[3].get_text(strip=True),
            })
        return cases

    def _get_total_pages(self) -> int:
        """Determine total number of pages from pagination."""
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 required")

        self.rate_limiter.wait()
        resp = self.client.get(f"{LIST_URL}?page=0")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        page_links = soup.select(f'a[href*="page="]')
        max_page = 0
        for link in page_links:
            href = link.get("href", "")
            match = re.search(r"page=(\d+)", href)
            if match:
                max_page = max(max_page, int(match.group(1)))
        return max_page + 1  # pages are 0-indexed

    def _get_case_detail(self, detail_url: str) -> Dict[str, Any]:
        """Fetch a case detail page and extract metadata + PDF links."""
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 required")

        self.rate_limiter.wait()
        resp = self.client.get(detail_url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract metadata from <dl>
        metadata = {}
        dl = soup.find("dl")
        if dl:
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            field_map = {
                "Začiatok konania:": "proceeding_start",
                "Účastníci konania:": "participants",
                "Typ konania:": "proceeding_type",
                "Praktika:": "legal_basis",
                "Sektor/relevantný trh:": "market_sector",
            }
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                if label in field_map:
                    metadata[field_map[label]] = dd.get_text(strip=True)

        # Extract title from h1
        h1 = soup.find("h1")
        if h1:
            metadata["title"] = h1.get_text(strip=True)

        # Extract decisions table (may have multiple decisions per case)
        decisions = []
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
                pdf_link = row.find("a", href=lambda h: h and ".pdf" in h)
                decisions.append({
                    "decision_date": cells[0].get_text(strip=True),
                    "decision_number": cells[1].get_text(strip=True),
                    "instance": cells[2].get_text(strip=True),
                    "verdict": cells[3].get_text(strip=True),
                    "effective_date": cells[4].get_text(strip=True),
                    "pdf_url": pdf_link["href"] if pdf_link else None,
                })

        metadata["decisions"] = decisions
        return metadata

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download a PDF and extract text."""
        try:
            text = extract_pdf_markdown(
                source="SK/PMU",
                source_id=pdf_url,
                pdf_url=f"{BASE_URL}{pdf_url}" if pdf_url.startswith("/") else pdf_url,
                table="case_law",
            )
            if text:
                return text
        except Exception as e:
            logger.debug(f"extract_pdf_markdown failed for {pdf_url}: {e}")

        # Fallback: direct pdfplumber extraction
        try:
            import pdfplumber
            self.rate_limiter.wait()
            full_url = f"{BASE_URL}{pdf_url}" if pdf_url.startswith("/") else pdf_url
            resp = self.client.get(full_url)
            resp.raise_for_status()
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages.append(page_text)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                return "\n\n".join(pages)
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return ""

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions from the PMÚ SR decision register."""
        total_pages = self._get_total_pages()
        logger.info(f"Found {total_pages} pages of decisions")

        for page in range(total_pages):
            logger.info(f"Fetching page {page + 1}/{total_pages}")
            cases = self._get_case_list_page(page)

            for case_summary in cases:
                detail_url = case_summary["detail_url"]
                try:
                    detail = self._get_case_detail(detail_url)
                except Exception as e:
                    logger.warning(f"Failed to fetch detail for {detail_url}: {e}")
                    continue

                # Yield one record per decision (a case may have multiple)
                for dec in detail.get("decisions", []):
                    if not dec.get("pdf_url"):
                        logger.debug(f"No PDF for decision {dec.get('decision_number')}")
                        continue

                    text = self._extract_pdf_text(dec["pdf_url"])
                    if not text:
                        logger.warning(f"Empty text for {dec.get('decision_number')}")
                        continue

                    yield {
                        "title": detail.get("title", case_summary.get("participant", "")),
                        "participants": detail.get("participants", case_summary.get("participant", "")),
                        "proceeding_type": detail.get("proceeding_type", case_summary.get("proceeding_type", "")),
                        "legal_basis": detail.get("legal_basis", ""),
                        "market_sector": detail.get("market_sector", ""),
                        "decision_number": dec["decision_number"],
                        "decision_date": dec["decision_date"],
                        "instance": dec["instance"],
                        "verdict": dec["verdict"],
                        "effective_date": dec.get("effective_date", ""),
                        "pdf_url": dec["pdf_url"],
                        "detail_url": detail_url,
                        "text": text,
                    }

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield decisions added since a given date."""
        since_str = since.strftime("%Y-%m-%d")
        for raw in self.fetch_all():
            decision_date = _parse_sk_date(raw.get("decision_date", ""))
            if decision_date and decision_date >= since_str:
                yield raw
            elif decision_date and decision_date < since_str:
                # Decisions are listed newest-first, so we can stop early
                break

    def normalize(self, raw: dict) -> dict:
        """Transform raw decision data into standard schema."""
        decision_number = raw.get("decision_number", "")
        decision_date = _parse_sk_date(raw.get("decision_date", ""))
        effective_date = _parse_sk_date(raw.get("effective_date", ""))

        detail_url = raw.get("detail_url", "")
        full_url = f"{BASE_URL}{detail_url}" if detail_url.startswith("/") else detail_url

        return {
            "_id": f"SK-PMU-{decision_number}",
            "_source": "SK/PMU",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": decision_date,
            "url": full_url,
            "decision_number": decision_number,
            "participants": raw.get("participants", ""),
            "proceeding_type": raw.get("proceeding_type", ""),
            "instance": raw.get("instance", ""),
            "verdict": raw.get("verdict", ""),
            "effective_date": effective_date,
            "legal_basis": raw.get("legal_basis", ""),
            "market_sector": raw.get("market_sector", ""),
            "pdf_url": f"{BASE_URL}{raw['pdf_url']}" if raw.get("pdf_url", "").startswith("/") else raw.get("pdf_url", ""),
        }


# ── CLI entry point ─────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="SK/PMU Decision Fetcher")
    parser.add_argument("command",
                        choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Sample mode: fetch only 10+ records")
    parser.add_argument("--full", action="store_true",
                        help="Full mode: fetch all records")
    args = parser.parse_args()

    source_dir = Path(__file__).parent
    scraper = PMUScraper(str(source_dir))

    if args.command == "test":
        logger.info("Testing connectivity to antimon.gov.sk...")
        try:
            resp = scraper.client.get(LIST_URL)
            resp.raise_for_status()
            logger.info(f"Connection OK — status {resp.status_code}, {len(resp.text)} bytes")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            sys.exit(1)

    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap_fast()
        logger.info(f"Bootstrap-fast complete: {json.dumps(stats, indent=2)}")

    elif args.command == "bootstrap":
        sample_mode = args.sample or not args.full
        stats = scraper.bootstrap(sample_mode=sample_mode)
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=30)
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
