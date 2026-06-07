#!/usr/bin/env python3
"""
INTL/UNILEX -- CISG & UNIDROIT Principles Case Law Database

Fetches case law from UNILEX (unilex.info), the database maintained by
UNIDROIT covering the CISG and UNIDROIT Principles.

Approach:
  1. Iterate through year pages /cisg/cases/date/<YEAR> to collect case IDs
  2. Fetch each case page /cisg/case/<ID>
  3. Parse metadata (date, country, court, parties), abstract, keywords, full text

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick test
"""

import re
import sys
import json
import time
import html as html_mod
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.UNILEX")

SOURCE_ID = "INTL/UNILEX"
SAMPLE_DIR = Path(__file__).parent / "sample"
BASE_URL = "https://www.unilex.info"

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DELAY = 2.0


def clean_html(text: str) -> str:
    """Strip HTML tags and clean text."""
    if not text:
        return ""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_mod.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_tab(html: str, tab_id: str) -> str:
    """Extract content from a tab pane by its id."""
    pattern = rf'id="{tab_id}"[^>]*class="tab-pane[^"]*"[^>]*>(.*?)(?=<div[^>]*class="tab-pane|</div>\s*</div>\s*</div>\s*</div>)'
    match = re.search(pattern, html, re.DOTALL)
    if match:
        return clean_html(match.group(1))
    return ""


class UNILEXScraper(BaseScraper):
    """Scraper for INTL/UNILEX — CISG & UNIDROIT Principles case law."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str) -> Optional[str]:
        """GET with retries and delay."""
        for attempt in range(3):
            try:
                time.sleep(DELAY)
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                wait = 5 * (attempt + 1)
                logger.warning("Attempt %d failed for %s: %s. Retry in %ds",
                               attempt + 1, url, e, wait)
                time.sleep(wait)
            except Exception as e:
                logger.error("Failed to fetch %s: %s", url, e)
                return None
        return None

    def _get_all_case_ids(self, instrument: str = "cisg") -> list:
        """Collect all case IDs by iterating year pages."""
        # First get the year index
        index_url = f"{BASE_URL}/{instrument}/cases/date/all"
        html = self._get(index_url)
        if not html:
            logger.error("Failed to fetch year index")
            return []

        years = sorted(set(re.findall(
            rf'/{instrument}/cases/date/(\d{{4}})', html
        )))
        logger.info("Found %d years: %s-%s", len(years),
                     years[0] if years else "?", years[-1] if years else "?")

        all_ids = []
        seen = set()
        for year in years:
            year_url = f"{BASE_URL}/{instrument}/cases/date/{year}"
            year_html = self._get(year_url)
            if not year_html:
                continue

            ids = re.findall(rf'/{instrument}/case/(\d+)', year_html)
            new_ids = [cid for cid in ids if cid not in seen]
            for cid in new_ids:
                seen.add(cid)
                all_ids.append(cid)

            logger.info("Year %s: %d new cases (total: %d)", year,
                         len(new_ids), len(all_ids))

        return all_ids

    def _parse_case(self, case_id: str, html: str,
                    instrument: str = "cisg") -> Optional[dict]:
        """Parse a case page into a structured dict."""
        # Extract metadata from dl-horizontal
        metadata = {}
        dl_match = re.search(
            r'<dl[^>]*class="dl-horizontal"[^>]*>(.*?)</dl>',
            html, re.DOTALL
        )
        if dl_match:
            terms = re.findall(
                r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>',
                dl_match.group(1), re.DOTALL
            )
            for dt, dd in terms:
                key = clean_html(dt).rstrip(":").strip().lower()
                val = clean_html(dd).strip()
                metadata[key] = val

        # Extract tab contents
        abstract = _extract_tab(html, "abstract")
        fulltext = _extract_tab(html, "fulltext")
        keywords = _extract_tab(html, "keywords")
        sources = _extract_tab(html, "sources")

        # Remove section headers from content
        for prefix in ["Abstract", "Fulltext", "Keywords", "Source"]:
            if abstract.startswith(prefix):
                abstract = abstract[len(prefix):].strip()
            if fulltext.startswith(prefix):
                fulltext = fulltext[len(prefix):].strip()
            if keywords.startswith(prefix):
                keywords = keywords[len(prefix):].strip()
            if sources.startswith(prefix):
                sources = sources[len(prefix):].strip()

        # Use full text if available, otherwise abstract
        text = fulltext if fulltext and len(fulltext) > 100 else abstract
        if not text or len(text) < 50:
            return None

        # Parse date (format: DD-MM-YYYY)
        raw_date = metadata.get("date", "")
        date_str = None
        date_match = re.match(r'(\d{2})-(\d{2})-(\d{4})', raw_date)
        if date_match:
            d, m, y = date_match.groups()
            try:
                datetime.strptime(f"{y}-{m}-{d}", "%Y-%m-%d")
                date_str = f"{y}-{m}-{d}"
            except ValueError:
                pass

        court = metadata.get("court", "")
        country = metadata.get("country", "")
        parties = metadata.get("parties", "")
        case_number = metadata.get("number", "")

        title_parts = []
        if parties:
            title_parts.append(parties)
        if court:
            title_parts.append(f"({court})")
        title = " ".join(title_parts) if title_parts else f"UNILEX Case {case_id}"

        return {
            "case_id": case_id,
            "instrument": instrument.upper(),
            "title": title,
            "text": text,
            "abstract": abstract[:2000] if abstract else "",
            "keywords": keywords,
            "date": date_str,
            "country": country,
            "court": court,
            "parties": parties,
            "case_number": case_number,
            "source_ref": sources,
        }

    def normalize(self, doc: dict) -> dict:
        """Transform a parsed record into the standard schema."""
        case_id = doc.get("case_id", "")
        instrument = doc.get("instrument", "CISG")

        return {
            "_id": f"UNILEX-{instrument}-{case_id}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": doc.get("title", ""),
            "text": doc.get("text", ""),
            "date": doc.get("date"),
            "url": f"{BASE_URL}/cisg/case/{case_id}",
            "language": "multi",
            "country": doc.get("country", ""),
            "court": doc.get("court", ""),
            "parties": doc.get("parties", ""),
            "case_number": doc.get("case_number", ""),
            "instrument": instrument,
            "abstract": doc.get("abstract", ""),
            "keywords": doc.get("keywords", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Fetch UNILEX cases."""
        sample_limit = 15 if sample else 999999
        count = 0

        # Get CISG case IDs
        if sample:
            # For sample, just fetch from recent years
            all_ids = []
            for year in ["2024", "2023", "2022", "2021", "2020"]:
                url = f"{BASE_URL}/cisg/cases/date/{year}"
                html = self._get(url)
                if html:
                    ids = list(set(re.findall(r'/cisg/case/(\d+)', html)))
                    all_ids.extend(ids)
                if len(all_ids) >= sample_limit:
                    break
            logger.info("Sample mode: collected %d case IDs from recent years",
                         len(all_ids))
        else:
            all_ids = self._get_all_case_ids("cisg")

        logger.info("Total case IDs to fetch: %d", len(all_ids))

        for case_id in all_ids:
            if count >= sample_limit:
                break

            url = f"{BASE_URL}/cisg/case/{case_id}"
            html = self._get(url)
            if not html:
                continue

            parsed = self._parse_case(case_id, html, "cisg")
            if not parsed:
                logger.warning("No usable text for case %s", case_id)
                continue

            record = self.normalize(parsed)
            yield record
            count += 1

            if count % 10 == 0:
                logger.info("Fetched %d records...", count)

        logger.info("Total records yielded: %d", count)

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Fetch recent cases."""
        logger.info("Fetching recent UNILEX cases")
        yield from self.fetch_all()


def main():
    scraper = UNILEXScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        logger.info("Testing UNILEX connectivity...")
        html = scraper._get(f"{BASE_URL}/cisg/case/2530")
        if not html:
            logger.error("Test FAILED")
            sys.exit(1)

        parsed = scraper._parse_case("2530", html, "cisg")
        if parsed:
            logger.info("Case OK — %d chars text, country=%s, court=%s",
                         len(parsed["text"]), parsed["country"], parsed["court"])
            logger.info("Title: %s", parsed["title"])
        else:
            logger.error("Parse FAILED")
            sys.exit(1)
        return

    if command in ("bootstrap", "bootstrap-fast"):
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            safe_id = record["_id"].replace("/", "_")[:100]
            fname = SAMPLE_DIR / f"{safe_id}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            if count % 50 == 0:
                logger.info("Saved %d records...", count)
        logger.info("Bootstrap complete: %d records saved to %s", count, SAMPLE_DIR)

    elif command == "update":
        since = (sys.argv[2] if len(sys.argv) > 2
                 and not sys.argv[2].startswith("-") else "2025-01-01")
        count = sum(1 for _ in scraper.fetch_updates(since))
        logger.info("Update complete: %d records since %s", count, since)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
