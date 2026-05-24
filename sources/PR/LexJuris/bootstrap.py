#!/usr/bin/env python3
"""
PR/LexJuris -- Puerto Rico Laws & Jurisprudence

Fetches Puerto Rico legislation with full text from lexjuris.com.

Strategy:
  - Iterate year menus (1997-2026): lexlex/Leyes{YEAR}/lexl{YEAR}Menu.htm
  - Parse each menu for individual law links: lexl{YEAR}{NUM}.htm
  - Fetch each law page, extract text from WordSection1 div
  - No robots.txt restrictions; 2-second crawl delay for politeness

Usage:
  python bootstrap.py bootstrap          # Fetch all legislation
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PR.LexJuris")

BASE_URL = "https://www.lexjuris.com/lexlex"
YEARS = list(range(2024, 1996, -1))  # Most recent first

# Spanish months for date parsing
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


class LexJurisScraper(BaseScraper):
    """Scraper for PR/LexJuris -- Puerto Rico legislation."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/worldwidelaw/legal-sources)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PR,es;q=0.9,en;q=0.5",
        })

    def _request(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        """HTTP GET with 2-second delay and retry."""
        for attempt in range(3):
            try:
                time.sleep(2)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 30s")
                    time.sleep(30)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                resp.encoding = "utf-8"
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(10)
        return None

    def _parse_menu_page(self, html: str, year: int) -> List[Dict[str, str]]:
        """Parse a year menu page for individual law links."""
        soup = BeautifulSoup(html, "html.parser")
        documents = []
        seen = set()

        pattern = re.compile(rf"lexl{year}\d{{3}}\.htm", re.IGNORECASE)
        links = soup.find_all("a", href=pattern)

        for link in links:
            href = link.get("href", "")
            # Normalize the href
            match = pattern.search(href)
            if not match:
                continue

            filename = match.group(0)
            if filename.lower() in seen:
                continue
            seen.add(filename.lower())

            # Extract law number from filename
            num_match = re.search(r"lexl\d{4}(\d{3})\.htm", filename, re.IGNORECASE)
            if not num_match:
                continue

            law_num = int(num_match.group(1))
            full_url = f"{BASE_URL}/Leyes{year}/{filename}"
            title = link.get_text(strip=True)

            documents.append({
                "url": full_url,
                "filename": filename,
                "law_number": law_num,
                "year": year,
                "title_from_menu": title,
            })

        # Sort by law number
        documents.sort(key=lambda d: d["law_number"])
        return documents

    def _extract_full_text(self, html: str) -> Dict[str, str]:
        """Extract full text and metadata from a law page."""
        soup = BeautifulSoup(html, "html.parser")
        result = {"text": "", "date": "", "title": ""}

        # Title from <title> tag
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # Full text from WordSection1 div
        ws = soup.find(class_="WordSection1")
        if ws:
            text = ws.get_text(separator="\n", strip=True)
        else:
            # Fallback: try #content div
            content = soup.select_one("#content")
            if content:
                text = content.get_text(separator="\n", strip=True)
            else:
                text = ""

        # Strip LexJuris copyright footer
        footer_idx = text.find("LexJuris de Puerto Rico")
        if footer_idx > 0:
            # Find the start of the footer paragraph
            prev_newline = text.rfind("\n", 0, footer_idx)
            if prev_newline > 0:
                # Look further back for the "Presione Aqui" line
                check_text = text[max(0, footer_idx - 500):footer_idx]
                prensa_idx = check_text.find("Presione Aqui")
                if prensa_idx >= 0:
                    text = text[:max(0, footer_idx - 500) + prensa_idx].rstrip()
                else:
                    text = text[:prev_newline].rstrip()

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        result["text"] = text.strip()

        # Extract date using Spanish date patterns
        # Pattern: "de DD de MONTH de YYYY"
        date_match = re.search(
            r"de\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(20\d{2}|19\d{2})",
            result["text"]
        )
        if date_match:
            day = int(date_match.group(1))
            month_name = date_match.group(2).lower()
            year = int(date_match.group(3))
            month = SPANISH_MONTHS.get(month_name)
            if month:
                try:
                    result["date"] = f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, TypeError):
                    pass

        return result

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        year = raw.get("year", 0)
        law_num = raw.get("law_number", 0)
        doc_id = f"PR-Ley-{year}-{law_num:03d}"

        return {
            "_id": doc_id,
            "_source": "PR/LexJuris",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "law_number": f"Ley Num. {law_num} de {year}",
            "url": raw.get("url", ""),
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all legislation from year menus."""
        count = 0

        for year in YEARS:
            menu_url = f"{BASE_URL}/Leyes{year}/lexl{year}Menu.htm"
            resp = self._request(menu_url)
            if resp is None:
                logger.info(f"No menu page for {year}, skipping")
                continue

            docs = self._parse_menu_page(resp.text, year)
            if not docs:
                logger.info(f"No laws found for {year}")
                continue

            logger.info(f"Year {year}: {len(docs)} laws found")

            for doc in docs:
                doc_resp = self._request(doc["url"])
                if doc_resp is None:
                    logger.warning(f"Failed to fetch: Ley {doc['law_number']} de {year}")
                    continue

                extracted = self._extract_full_text(doc_resp.text)
                if not extracted["text"] or len(extracted["text"]) < 200:
                    logger.warning(
                        f"Insufficient text for Ley {doc['law_number']} de {year}: "
                        f"{len(extracted['text'])} chars"
                    )
                    continue

                raw = {
                    "year": year,
                    "law_number": doc["law_number"],
                    "title": extracted["title"] or doc.get("title_from_menu", ""),
                    "text": extracted["text"],
                    "date": extracted["date"],
                    "url": doc["url"],
                }
                count += 1
                yield raw

        logger.info(f"Completed: {count} laws fetched")

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        """Fetch recent legislation (current year only)."""
        current_year = datetime.now().year
        menu_url = f"{BASE_URL}/Leyes{current_year}/lexl{current_year}Menu.htm"
        resp = self._request(menu_url)
        if resp is None:
            logger.info(f"No menu page for {current_year}")
            return

        docs = self._parse_menu_page(resp.text, current_year)
        count = 0
        for doc in docs:
            doc_resp = self._request(doc["url"])
            if doc_resp is None:
                continue

            extracted = self._extract_full_text(doc_resp.text)
            if not extracted["text"] or len(extracted["text"]) < 200:
                continue

            raw = {
                "year": current_year,
                "law_number": doc["law_number"],
                "title": extracted["title"] or doc.get("title_from_menu", ""),
                "text": extracted["text"],
                "date": extracted["date"],
                "url": doc["url"],
            }
            count += 1
            yield raw

        logger.info(f"Updates: {count} laws fetched for {current_year}")

    def test(self) -> bool:
        """Quick connectivity test."""
        menu_url = f"{BASE_URL}/Leyes2024/lexl2024Menu.htm"
        resp = self._request(menu_url)
        if resp is None:
            logger.error("Cannot reach LexJuris menu page")
            return False

        docs = self._parse_menu_page(resp.text, 2024)
        if not docs:
            logger.error("No laws found on 2024 menu page")
            return False

        logger.info(f"Menu OK: {len(docs)} laws for 2024")

        # Test fetching one law
        doc_resp = self._request(docs[0]["url"])
        if doc_resp:
            extracted = self._extract_full_text(doc_resp.text)
            logger.info(
                f"Doc OK: Ley {docs[0]['law_number']} ({len(extracted['text'])} chars)"
            )
            return True

        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PR/LexJuris data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "update", "test"],
        help="Command to run",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Only fetch a small sample (for validation)",
    )
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = LexJurisScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    elif args.command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        max_records = 15 if args.sample else None
        count = 0

        for raw in scraper.fetch_all():
            record = scraper.normalize(raw)
            out_path = sample_dir / f"record_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            text_len = len(record.get("text", ""))
            logger.info(
                f"[{count + 1}] {record.get('title', '?')[:80]} "
                f"({text_len:,} chars)"
            )

            count += 1
            if max_records and count >= max_records:
                break

        logger.info(f"Bootstrap complete: {count} records saved to {sample_dir}")

    elif args.command == "update":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for raw in scraper.fetch_updates():
            record = scraper.normalize(raw)
            out_path = sample_dir / f"update_{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
        logger.info(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
