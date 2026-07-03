#!/usr/bin/env python3
"""
INTL/AU-HumanRightsCommission -- African Commission on Human and Peoples' Rights
Decisions on Communications

Scrapes the ACHPR website listing pages, follows individual decision URLs,
downloads linked PDFs, and extracts full text via pdfplumber.

~400 decisions (merits, admissibility, strike-outs) since 1988.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import urljoin

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
logger = logging.getLogger("legal-data-hunter.INTL.AU-HumanRightsCommission")

BASE_URL = "https://achpr.au.int"
LISTING_URL = f"{BASE_URL}/en/category/decisions-communications"
SOURCE_ID = "INTL/AU-HumanRightsCommission"


class ACHPRScraper(BaseScraper):
    """
    Scraper for INTL/AU-HumanRightsCommission -- ACHPR Decisions.
    Country: INTL
    URL: https://achpr.au.int/en/category/decisions-communications

    Data types: case_law
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html, application/xhtml+xml, */*",
        })

    def _fetch_listing_page(self, page: int = 0) -> list[dict]:
        """
        Fetch one listing page and return list of dicts with
        'url', 'title', 'status', 'session' for each decision.
        """
        url = f"{LISTING_URL}?page={page}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        decisions = []

        # Look for decision links in the listing
        # The listing page contains article/card elements with links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Decision URLs contain /decisions-communications/ and a slug
            if "/decisions-communications/" not in href:
                continue
            # Skip the category page itself
            if href.rstrip("/").endswith("decisions-communications") or \
               href.rstrip("/").endswith("category/decisions-communications"):
                continue

            full_url = urljoin(BASE_URL, href)
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Remove /index.php/ prefix if present
            full_url = full_url.replace("/index.php/", "/")
            decisions.append({
                "url": full_url,
                "title": title,
            })

        # Deduplicate by URL
        seen = set()
        unique = []
        for d in decisions:
            if d["url"] not in seen:
                seen.add(d["url"])
                unique.append(d)

        return unique

    def _has_next_page(self, page: int) -> bool:
        """Check if a next page exists by looking for Load More link."""
        url = f"{LISTING_URL}?page={page}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return f"?page={page + 1}" in resp.text

    # Month names for date extraction
    EN_MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    FR_MONTHS = {
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    }

    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """Extract the most relevant date from text (PDF or HTML body)."""
        if not text:
            return None
        # Normalize whitespace for multi-line date patterns
        clean = re.sub(r'\s+', ' ', text)

        candidates = []

        # English dates: "9 November 2023"
        for m in re.finditer(
            r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            clean, re.IGNORECASE
        ):
            day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = self.EN_MONTHS.get(month_name)
            if month and 1988 <= year <= 2030 and 1 <= day <= 31:
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")

        # French dates: "30 juillet 2025"
        for m in re.finditer(
            r'(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)\s+(\d{4})',
            clean, re.IGNORECASE
        ):
            day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = self.FR_MONTHS.get(month_name)
            if month and 1988 <= year <= 2030 and 1 <= day <= 31:
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")

        # Session end date: "held from X to Y Month YYYY"
        for m in re.finditer(
            r'(?:held\s+(?:from\s+)?\d{1,2}(?:st|nd|rd|th)?\s+to\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            clean, re.IGNORECASE
        ):
            day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = self.EN_MONTHS.get(month_name)
            if month and 1988 <= year <= 2030:
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")

        if not candidates:
            return None

        # Return the most recent date (latest decision date is most relevant)
        # Filter out dates from the African Charter (June 1981, Nov 1987)
        filtered = [d for d in candidates if d > "1988-01-01"]
        if filtered:
            return max(filtered)
        return max(candidates)

    def _fetch_decision_page(self, url: str) -> dict:
        """
        Fetch an individual decision page and extract metadata + PDF URL.
        Returns dict with title, communication_number, session, date, status, pdf_url, body_text.
        """
        # Try English version first, fall back to original language
        en_url = url.replace("/fr/", "/en/").replace("/ar/", "/en/").replace("/sw/", "/en/").replace("/pt/", "/en/")

        urls_to_try = [en_url] if en_url != url else [url]
        if en_url != url:
            urls_to_try.append(url)

        resp = None
        for try_url in urls_to_try:
            r = self.session.get(try_url, timeout=30)
            if r.status_code == 200:
                resp = r
                break
        if resp is None:
            # Last attempt already has the error
            r.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        result = {"page_url": resp.url}

        # Title
        h1 = soup.find("h1")
        if h1:
            result["title"] = h1.get_text(strip=True)

        # Extract communication number from title or URL
        title_text = result.get("title", "")
        comm_match = re.search(r'(\d+/\d+)', title_text)
        if comm_match:
            result["communication_number"] = comm_match.group(1)
        else:
            slug_match = re.search(r'(\d+)', url.split("/")[-1])
            if slug_match:
                result["communication_number"] = slug_match.group(1)

        # Body text from the page
        body_text_parts = []
        content_div = soup.find("div", class_="field--name-body") or \
                      soup.find("article") or \
                      soup.find("div", class_="node__content")
        if content_div:
            for p in content_div.find_all(["p", "li", "h2", "h3", "h4"]):
                t = p.get_text(strip=True)
                if t:
                    body_text_parts.append(t)
        result["body_text"] = "\n\n".join(body_text_parts)

        # PDF download links
        pdf_urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                pdf_urls.append(urljoin(BASE_URL, href))

        # Prefer English PDFs
        en_pdfs = [u for u in pdf_urls if "-en" in u.lower() or "eng" in u.lower()]
        result["pdf_url"] = en_pdfs[0] if en_pdfs else (pdf_urls[0] if pdf_urls else None)
        result["all_pdf_urls"] = pdf_urls

        # Extract date from the HTML page text
        page_text = soup.get_text()
        result["date"] = self._extract_date_from_text(page_text)

        # Session info
        session_match = re.search(
            r'(\d+(?:st|nd|rd|th)\s+(?:Ordinary|Private|Extra[-\s]?ordinary)\s+Session[^.]{0,120}\d{4})',
            page_text, re.IGNORECASE
        )
        if session_match:
            result["session"] = session_match.group(1).strip()

        # Decision status
        for status_kw in ["Decided on merits", "Ruled inadmissible", "Inadmissible",
                          "Strike Out", "Struck Out", "Withdrawn", "Admissible",
                          "Review on Admissibility", "Seized", "Friendly Settlement"]:
            if status_kw.lower() in page_text.lower():
                result["status"] = status_kw
                break

        return result

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract text using pdfplumber."""
        try:
            resp = self.session.get(pdf_url, timeout=120)
            resp.raise_for_status()
            if len(resp.content) < 500:
                return None
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
                return "\n\n".join(pages_text) if pages_text else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decision page data by paginating through listings."""
        page = 0
        total_yielded = 0
        consecutive_empty = 0

        while consecutive_empty < 3:
            logger.info(f"Fetching listing page {page}...")
            try:
                decisions = self._fetch_listing_page(page)
            except Exception as e:
                logger.error(f"Failed to fetch listing page {page}: {e}")
                break

            if not decisions:
                consecutive_empty += 1
                page += 1
                time.sleep(1)
                continue

            consecutive_empty = 0
            for dec in decisions:
                yield dec
                total_yielded += 1

            page += 1
            time.sleep(1.5)

        logger.info(f"Found {total_yielded} decision URLs across {page} pages")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield recently updated decisions."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> Optional[dict]:
        """
        Fetch the individual decision page, download PDF, extract text,
        and return normalized record.
        """
        url = raw.get("url", "")
        if not url:
            return None

        # Fetch individual decision page
        try:
            self.rate_limiter.wait()
            page_data = self._fetch_decision_page(url)
        except Exception as e:
            logger.warning(f"Failed to fetch decision page {url}: {e}")
            return None

        # Get full text from PDF
        text = None
        pdf_url = page_data.get("pdf_url")
        if pdf_url:
            self.rate_limiter.wait()
            text = self._extract_pdf_text(pdf_url)

        # Fall back to page body text if PDF fails
        if not text or len(text) < 100:
            body = page_data.get("body_text", "")
            if len(body) >= 200:
                text = body
                pdf_url = None

        if not text or len(text) < 100:
            logger.debug(f"Skipping {url}: no usable text")
            return None

        title = page_data.get("title", raw.get("title", ""))
        comm_num = page_data.get("communication_number", "")
        session = page_data.get("session", "")
        status = page_data.get("status", "")

        # Date: try HTML page first, then PDF text, then communication year
        date = page_data.get("date")
        if not date and text:
            date = self._extract_date_from_text(text)
        if not date and comm_num:
            # Use year from communication number (e.g., 424/12 -> 2012)
            year_match = re.search(r'/(\d{2,4})$', comm_num)
            if year_match:
                y = int(year_match.group(1))
                if y < 100:
                    y += 2000 if y < 50 else 1900
                date = f"{y}-01-01"

        # Build a stable ID from communication number or URL slug
        if comm_num:
            record_id = f"ACHPR-{comm_num.replace('/', '-')}"
        else:
            slug = url.rstrip("/").split("/")[-1]
            record_id = f"ACHPR-{slug}"

        return {
            "_id": record_id,
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url,
            "communication_number": comm_num,
            "session": session,
            "status": status,
            "pdf_url": pdf_url,
        }


def main():
    parser = argparse.ArgumentParser(description="INTL/AU-HumanRightsCommission bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch only sample records")
    parser.add_argument("--full", action="store_true", help="Full bootstrap (default)")
    args = parser.parse_args()

    scraper = ACHPRScraper()

    if args.command == "test":
        logger.info("Testing ACHPR website connectivity...")
        try:
            decisions = scraper._fetch_listing_page(0)
            logger.info(f"Listing OK: {len(decisions)} decisions on page 0")
            if decisions:
                logger.info(f"First: {decisions[0]['title'][:80]}")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            sys.exit(1)
        return

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = args.sample
        stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=15)
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")
    elif args.command == "update":
        since = datetime.now(timezone.utc).replace(day=1)
        stats = scraper.bootstrap(sample_mode=False)
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
