#!/usr/bin/env python3
"""
INTL/UN-AVL -- UN Audiovisual Library of International Law

Fetches scholarly introductory notes and procedural histories for 100+
major international legal instruments from legal.un.org/avl/.

Strategy:
  - Discover all instrument codes from the master list at /avl/ha/instruments.html
  - Fetch each instrument page (e.g., /avl/ha/udhr/udhr.html)
  - Extract English introductory note + procedural history from TabbedPanels HTML
  - ~114 instruments total

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import re
import sys
import json
import time
import logging
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
logger = logging.getLogger("legal-data-hunter.INTL.UN-AVL")

BASE_URL = "https://legal.un.org/avl"
INSTRUMENTS_URL = f"{BASE_URL}/ha/instruments.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}


class UNAVLScraper(BaseScraper):
    SOURCE_ID = "INTL/UN-AVL"

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch_page(self, url: str) -> Optional[str]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30, allow_redirects=False)
                if resp.status_code == 302:
                    logger.warning("Redirect (page moved): %s", url)
                    return None
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if attempt == 2:
                    logger.warning("Failed to fetch %s: %s", url, e)
                    return None
                time.sleep(2 * (attempt + 1))

    def _discover_instruments(self) -> List[Dict]:
        """Discover all instruments from the master list page."""
        logger.info("Fetching instrument list from %s", INSTRUMENTS_URL)
        html = self._fetch_page(INSTRUMENTS_URL)
        if not html:
            logger.error("Could not fetch instruments list")
            return []

        soup = BeautifulSoup(html, "html.parser")
        instruments = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.match(r"^([a-zA-Z0-9_-]+)/\1\.html$", href)
            if m:
                code = m.group(1)
                title = a.get_text(strip=True)
                if code not in seen and title:
                    seen.add(code)
                    instruments.append({
                        "code": code,
                        "title": title,
                        "url": f"{BASE_URL}/ha/{code}/{code}.html",
                    })

        logger.info("Discovered %d instruments", len(instruments))
        return instruments

    def _extract_text_from_panel(self, panel) -> str:
        """Extract the English text from a TabbedPanelsContent div.

        The panel contains:
        - A header div (P_HA_DocumentsTabs) with author info
        - A language selector table
        - The English text body in a plain div
        """
        # Look for the main content div (without special class, with substantial text)
        divs = panel.find_all("div", recursive=False)
        best_text = ""
        for d in divs:
            cls = d.get("class", [])
            if "P_HA_DocumentsTabs" in cls:
                continue
            text = d.get_text(separator="\n", strip=True)
            if len(text) > len(best_text):
                best_text = text

        # If no div found, try extracting from the panel itself
        if not best_text:
            full = panel.get_text(separator="\n", strip=True)
            # Try to find English text start markers
            for marker in ["When ", "The ", "On ", "In ", "At the ", "This ", "Article "]:
                idx = full.find(marker)
                if idx > 0 and idx < 500:
                    best_text = full[idx:]
                    break
            if not best_text:
                best_text = full

        # Clean up the text
        best_text = re.sub(r"\n{3,}", "\n\n", best_text)
        return best_text.strip()

    def _extract_author(self, panel) -> str:
        """Extract the author from the P_HA_DocumentsTabs div."""
        header = panel.find("div", class_="P_HA_DocumentsTabs")
        if header:
            text = header.get_text(strip=True)
            # Pattern: "By Author Name, Title"
            m = re.match(r"^By\s+(.+?)(?:\s*$)", text)
            if m:
                return m.group(1)
            return text
        return ""

    def _extract_date(self, title: str, text: str) -> Optional[str]:
        """Extract a year from the title or opening text."""
        combined = f"{title} {text[:500]}"
        years = re.findall(r"\b(18\d{2}|19\d{2}|20[0-2]\d)\b", combined)
        if years:
            return f"{years[0]}-01-01"
        return None

    def _process_instrument(self, inst: Dict) -> Optional[Dict]:
        """Fetch and parse a single instrument page."""
        html = self._fetch_page(inst["url"])
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        panels = soup.find_all("div", class_="TabbedPanelsContent")

        if not panels:
            logger.warning("No tabbed panels found for %s", inst["code"])
            return None

        # Panel 0 = Introductory Note
        intro_text = ""
        author = ""
        if len(panels) > 0:
            intro_text = self._extract_text_from_panel(panels[0])
            author = self._extract_author(panels[0])

        # Panel 1 = Procedural History
        proc_text = ""
        if len(panels) > 1:
            proc_text = self._extract_text_from_panel(panels[1])

        # Combine into full text
        parts = []
        if intro_text:
            parts.append(f"INTRODUCTORY NOTE\n\n{intro_text}")
        if proc_text:
            parts.append(f"PROCEDURAL HISTORY\n\n{proc_text}")

        full_text = "\n\n---\n\n".join(parts)

        if len(full_text) < 100:
            logger.warning("Insufficient text for %s (%d chars)", inst["code"], len(full_text))
            return None

        return {
            "code": inst["code"],
            "title": inst["title"],
            "url": inst["url"],
            "author": author,
            "text": full_text,
            "intro_text": intro_text,
            "proc_text": proc_text,
        }

    def test_connection(self) -> bool:
        try:
            html = self._fetch_page(INSTRUMENTS_URL)
            if html and "Audiovisual" in html:
                logger.info("Connection OK: UN AVL instruments page accessible")
                return True
            return False
        except Exception as e:
            logger.error("Connection failed: %s", e)
            return False

    def fetch_all(self) -> Generator[Dict, None, None]:
        instruments = self._discover_instruments()
        if not instruments:
            logger.error("No instruments discovered")
            return

        logger.info("Processing %d instruments...", len(instruments))
        for i, inst in enumerate(instruments):
            logger.info("[%d/%d] %s", i + 1, len(instruments), inst["title"][:70])
            self.rate_limiter.wait()

            result = self._process_instrument(inst)
            if result:
                yield result
            else:
                logger.warning("Skipped: %s", inst["code"])

    def fetch_updates(self, since: datetime) -> Generator[Dict, None, None]:
        return
        yield

    def normalize(self, raw: dict) -> dict:
        date_str = self._extract_date(raw["title"], raw.get("text", ""))

        return {
            "_id": f"UN-AVL-{raw['code']}",
            "_source": "INTL/UN-AVL",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": date_str,
            "url": raw["url"],
            "author": raw.get("author", ""),
            "category": "international_law",
        }

    def run_bootstrap(self, sample: bool = False):
        sample_dir = self.source_dir / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for raw in self.fetch_all():
            normalized = self.normalize(raw)
            fname = re.sub(r"[^\w\-.]", "_", f"{normalized['_id'][:80]}.json")
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            count += 1
            logger.info("  -> %d chars of text", len(normalized["text"]))

            if sample and count >= 15:
                break

        logger.info("Bootstrap complete: %d records saved", count)
        return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/UN-AVL Bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = UNAVLScraper()

    if args.command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.run_bootstrap(sample=args.sample)
    elif args.command == "update":
        scraper.run_bootstrap(sample=False)


if __name__ == "__main__":
    main()
