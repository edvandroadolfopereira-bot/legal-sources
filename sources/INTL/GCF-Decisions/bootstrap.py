#!/usr/bin/env python3
"""
INTL/GCF-Decisions -- Green Climate Fund Board Decisions

Fetches all GCF Board decisions from greenclimate.fund/boardroom/decisions.
~877 decisions from B.01 (2012) through B.44 (2026).

Strategy:
  - Paginate /boardroom/decisions?page=0..17 to collect all decision slugs
  - Fetch each /decision/{slug} page for full text
  - Extract metadata (decision number, date, meeting, type) and clean HTML

Usage:
    python bootstrap.py bootstrap --sample   # Fetch 15 sample records
    python bootstrap.py bootstrap --full     # Full fetch all decisions
    python bootstrap.py bootstrap-fast       # Alias for bootstrap --full
    python bootstrap.py test                 # Quick connectivity test
"""

import json
import logging
import re
import sys
import time
import html as html_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.GCF-Decisions")

BASE_URL = "https://www.greenclimate.fund"
LIST_URL = f"{BASE_URL}/boardroom/decisions"
RATE_LIMIT = 1.5
TOTAL_PAGES = 18


class GCFDecisionsScraper(BaseScraper):
    """Scraper for INTL/GCF-Decisions."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })

    def _fetch_decision_slugs(self) -> list[str]:
        """Paginate the decisions listing to collect all decision URL slugs."""
        all_slugs = []
        seen = set()
        for page in range(TOTAL_PAGES):
            url = f"{LIST_URL}?page={page}"
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning(f"Error fetching page {page}: {e}")
                continue

            links = re.findall(r'href="/decision/([^"]+)"', resp.text)
            for slug in links:
                if slug not in seen:
                    seen.add(slug)
                    all_slugs.append(slug)

            logger.info(f"Page {page}: {len(links)} links, total unique: {len(all_slugs)}")
            time.sleep(RATE_LIMIT)

        logger.info(f"Total decision slugs collected: {len(all_slugs)}")
        return all_slugs

    def _parse_decision_page(self, slug: str) -> Optional[dict]:
        """Fetch and parse a single decision page."""
        url = f"{BASE_URL}/decision/{slug}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Error fetching decision {slug}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract metadata from field wrappers
        decision_type = ""
        decision_date = ""
        meeting = ""
        title_text = ""

        # Decision type field
        dt_el = soup.find("div", class_="field-name-field-decision-type")
        if dt_el:
            items = dt_el.find("div", class_="field-items")
            if items:
                decision_type = items.get_text(strip=True)

        # Decision date field
        dd_el = soup.find("div", class_="field-name-field-decision-date")
        if dd_el:
            items = dd_el.find("div", class_="field-items")
            if items:
                decision_date = items.get_text(strip=True)

        # Extract from article content
        article = soup.find("article")
        if not article:
            logger.warning(f"No article element found for {slug}")
            return None

        # Get all text from article
        # Remove style/script tags first
        for tag in article.find_all(["style", "script"]):
            tag.decompose()

        lines = []
        for el in article.stripped_strings:
            lines.append(str(el))

        if not lines:
            logger.warning(f"No content for {slug}")
            return None

        # Parse the structured content
        # Typical structure: "Decision type", value, "Decision date", value, "at B.XX",
        # "Decisions", "B.XX/YY: Title", then the decision text
        full_text_parts = []
        title_found = False
        in_body = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip metadata labels
            if line_stripped in ("Decision type", "Decision date", "Decisions", "Share"):
                continue

            # Skip decision type value if already captured
            if line_stripped == decision_type and not in_body:
                continue

            # Parse "at B.XX" for meeting reference
            if re.match(r'^at B\.\d+', line_stripped) and not meeting:
                meeting = line_stripped.replace("at ", "")
                continue

            # Date value (e.g., "04 Mar 2024")
            if re.match(r'^\d{2}\s+\w{3}\s+\d{4}$', line_stripped) and not in_body:
                if not decision_date:
                    decision_date = line_stripped
                continue

            # Title line: "B.XX/YY: Title text"
            if re.match(r'^B\.\d+/\d+:', line_stripped) or re.match(r'^B\.BM-\d+-?\d*/\d+:', line_stripped):
                title_text = line_stripped
                in_body = True
                full_text_parts.append(line_stripped)
                continue

            # Decision number without colon (e.g. "B.BM-2026/05")
            if re.match(r'^B\.(BM-)?[\d-]+/\d+$', line_stripped) and not in_body:
                continue

            if in_body:
                full_text_parts.append(line_stripped)

        # If we never found a title pattern, use all non-metadata lines
        if not full_text_parts:
            skip_labels = {"Decision type", "Decision date", "Decisions", "Share",
                           "In-session", "Between meetings"}
            for line in lines:
                ls = line.strip()
                if ls and ls not in skip_labels and not re.match(r'^at B\.\d+', ls):
                    if re.match(r'^\d{2}\s+\w{3}\s+\d{4}$', ls):
                        continue
                    full_text_parts.append(ls)

        full_text = "\n".join(full_text_parts).strip()

        # Remove trailing "Share" and social media artifacts
        full_text = re.sub(r'\nShare\s*$', '', full_text)
        full_text = re.sub(r'\n(Facebook|Twitter|LinkedIn|Email)\s*', '', full_text)

        # Remove "Annex" download artifacts but keep annex text references
        full_text = re.sub(r'\n(PDF|XLS|XLSX|DOC)\s*\n\|\s*\n[\d.]+\s*(KB|MB)\s*', '\n', full_text)

        if not full_text or len(full_text) < 30:
            logger.warning(f"Insufficient text for {slug}: {len(full_text)} chars")
            return None

        # Extract meeting from slug if not found
        if not meeting:
            m = re.match(r'b(\d+)-', slug)
            if m:
                meeting = f"B.{m.group(1)}"
            else:
                m = re.match(r'bbm-(\d{4})-(\d+)', slug)
                if m:
                    meeting = f"B.BM-{m.group(1)}/{m.group(2)}"

        # Extract decision number from title or slug
        decision_no = ""
        if title_text:
            m = re.match(r'(B\.[^\s:]+)', title_text)
            if m:
                decision_no = m.group(1).rstrip(":")
        if not decision_no:
            # Derive from slug
            decision_no = slug.upper().replace("-", "/", 1).replace("B", "B.", 1)

        return {
            "slug": slug,
            "decision_no": decision_no,
            "title": title_text or f"GCF Decision {decision_no}",
            "text": full_text,
            "date_raw": decision_date,
            "meeting": meeting,
            "decision_type": decision_type,
            "url": url,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all GCF board decisions."""
        slugs = self._fetch_decision_slugs()
        for i, slug in enumerate(slugs):
            try:
                time.sleep(RATE_LIMIT)
                result = self._parse_decision_page(slug)
                if result:
                    yield result
                    logger.info(f"Fetched {i+1}/{len(slugs)}: {result['decision_no']} ({len(result['text'])} chars)")
                else:
                    logger.warning(f"Skipped {i+1}/{len(slugs)}: {slug}")
            except Exception as e:
                logger.error(f"Error on {slug}: {e}")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Fetch decisions from recent meetings only."""
        # For updates, just re-fetch the first page (most recent decisions)
        slugs = []
        seen = set()
        try:
            resp = self.session.get(LIST_URL, timeout=30)
            resp.raise_for_status()
            links = re.findall(r'href="/decision/([^"]+)"', resp.text)
            for slug in links:
                if slug not in seen:
                    seen.add(slug)
                    slugs.append(slug)
        except requests.RequestException as e:
            logger.error(f"Error fetching updates: {e}")
            return

        for slug in slugs:
            time.sleep(RATE_LIMIT)
            result = self._parse_decision_page(slug)
            if result:
                yield result

    def normalize(self, raw: dict) -> Optional[dict]:
        """Transform raw GCF decision into standardized schema."""
        text = raw.get("text", "")
        if not text or len(text) < 30:
            return None

        slug = raw.get("slug", "")
        decision_no = raw.get("decision_no", slug)
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', decision_no)

        # Parse date
        date_iso = self._parse_date(raw.get("date_raw", ""))

        title = raw.get("title", "")
        if not title:
            title = f"GCF Decision {decision_no}"

        return {
            "_id": f"INTL-GCF-{safe_id}",
            "_source": "INTL/GCF-Decisions",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_iso,
            "url": raw.get("url", f"{BASE_URL}/decision/{slug}"),
            "decision_no": decision_no,
            "meeting": raw.get("meeting", ""),
            "decision_type": raw.get("decision_type", ""),
        }

    @staticmethod
    def _parse_date(date_raw: str) -> Optional[str]:
        """Parse GCF date format like '04 Mar 2024' to ISO."""
        if not date_raw:
            return None
        # Try "DD Mon YYYY"
        try:
            dt = datetime.strptime(date_raw.strip(), "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        # Try "Month DD, YYYY"
        try:
            dt = datetime.strptime(date_raw.strip(), "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        return None


if __name__ == "__main__":
    scraper = GCFDecisionsScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample] [--full]")
        sys.exit(1)

    cmd = sys.argv[1]
    sample = "--sample" in sys.argv

    if cmd == "test":
        print("Testing GCF Decisions connectivity...")
        try:
            resp = scraper.session.get(LIST_URL, timeout=30)
            resp.raise_for_status()
            slugs = re.findall(r'href="/decision/([^"]+)"', resp.text)
            print(f"OK: Found {len(slugs)} decision links on page 1")
            if slugs:
                result = scraper._parse_decision_page(slugs[0])
                if result and len(result.get("text", "")) > 30:
                    print(f"OK: Decision {result['decision_no']} has {len(result['text'])} chars")
                else:
                    print("WARN: First decision has no/short text")
        except Exception as e:
            print(f"FAIL: {e}")
            sys.exit(1)

    elif cmd in ("bootstrap", "bootstrap-fast"):
        stats = scraper.bootstrap(sample_mode=sample, sample_size=15)
        fetched = stats.get("records_fetched", 0) or stats.get("sample_records_saved", 0)
        logger.info(f"Bootstrap complete: {fetched} records — {stats}")
        if fetched == 0:
            sys.exit(1)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
