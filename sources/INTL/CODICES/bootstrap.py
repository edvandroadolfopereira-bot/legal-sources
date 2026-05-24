#!/usr/bin/env python3
"""
INTL/CODICES -- Venice Commission Constitutional Case Law Database

Fetches constitutional court decisions from the CODICES database
maintained by the Venice Commission (Council of Europe).

Strategy:
  - POST /api/search to paginate through all précis (50 per page)
  - GET /api/precis/{guid}?lang=eng to fetch full document details
  - Extract summary text from EN and FR translations
  - ~10,000 decisions from 100+ courts worldwide

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import time
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
logger = logging.getLogger("legal-data-hunter.INTL.CODICES")

API_BASE = "https://codices.coe.int/api"

# Full search request body matching the Angular SPA's SearchRequestDto
SEARCH_TEMPLATE = {
    "Text": "",
    "Type": None,
    "WithProximity": False,
    "ProximitySize": 10,
    "ReferenceCode": "",
    "DecisionNumber": "",
    "Title": "",
    "Continent": None,
    "Country": None,
    "StartDate": None,
    "EndDate": None,
    "LanguageCode": "",
    "Group": None,
    "ThesaurusIndexNumber": "",
    "ThesaurusText": "",
    "AlphaIndexText": "",
    "WithThesaurusChildren": True,
    "CountryFilterList": [],
    "ThesaurusFilterList": [],
    "TreePathList": ["PRECIS"],
    "Page": 0,
    "Size": 50,
}


class CODICESScraper(BaseScraper):
    """
    Scraper for INTL/CODICES -- Venice Commission CODICES database.
    Country: INTL
    URL: https://codices.coe.int/

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
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://codices.coe.int",
            "Referer": "https://codices.coe.int/",
        })

    def _search(self, page: int = 0, size: int = 50, **overrides) -> dict:
        """Execute a search against the CODICES API."""
        body = {**SEARCH_TEMPLATE, "Page": page, "Size": size, **overrides}
        r = self.session.post(f"{API_BASE}/search", json=body, timeout=60)
        r.raise_for_status()
        return r.json()

    def _get_precis(self, guid: str, lang: str = "eng") -> dict:
        """Fetch a single précis by GUID."""
        r = self.session.get(
            f"{API_BASE}/precis/{guid}",
            params={"lang": lang},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    def _extract_text(self, precis: dict) -> str:
        """Extract the best available text from a précis document."""
        parts = []

        translations = precis.get("precisTranslations", {})

        # Prefer English, fall back to French
        for lang_key in ("eng", "fra"):
            tr = translations.get(lang_key, {})
            if not tr:
                continue

            head_note = (tr.get("headNote") or "").strip()
            summary = (tr.get("summary") or "").strip()

            if head_note:
                parts.append(head_note)
            if summary:
                parts.append(summary)

            if parts:
                break

        return "\n\n".join(parts)

    def _extract_title(self, precis: dict) -> str:
        """Extract the title from a précis."""
        ref = precis.get("referenceCode", "")
        translations = precis.get("precisTranslations", {})

        for lang_key in ("eng", "fra"):
            tr = translations.get(lang_key, {})
            if tr:
                title = (tr.get("title") or "").strip()
                if title:
                    return f"{ref} — {title}" if ref else title

        return ref or precis.get("id", "unknown")

    def _extract_date(self, precis: dict) -> Optional[str]:
        """Extract the decision date as ISO string."""
        date_str = precis.get("decisionDate")
        if not date_str:
            return None
        # API returns ISO format like "2024-01-15T00:00:00"
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return date_str[:10] if len(date_str) >= 10 else None

    def _extract_court(self, precis: dict) -> str:
        """Extract the court name from translations."""
        translations = precis.get("precisTranslations", {})
        for lang_key in ("eng", "fra"):
            tr = translations.get(lang_key, {})
            if tr:
                name = (tr.get("courtName") or "").strip()
                if name:
                    return name
        return ""

    def _extract_country(self, precis: dict) -> str:
        """Extract the country name from translations or code."""
        translations = precis.get("precisTranslations", {})
        for lang_key in ("eng", "fra"):
            tr = translations.get(lang_key, {})
            if tr:
                name = (tr.get("countryName") or "").strip()
                if name:
                    return name
        country = precis.get("country", "")
        return str(country) if country else ""

    def normalize(self, raw: dict) -> dict:
        """Transform raw précis into standard schema."""
        # Extract thesaurus labels from nested translations
        thesaurus_labels = []
        for t in raw.get("thesaurus", []):
            if isinstance(t, dict):
                translations = t.get("thesaurusTranslations", {})
                for lang_key in ("eng", "fra"):
                    tr = translations.get(lang_key, {})
                    if tr:
                        label = (tr.get("text") or "").strip()
                        if label:
                            thesaurus_labels.append(label)
                            break

        # Determine language of the précis text used
        translations = raw.get("precisTranslations", {})
        lang = "eng" if translations.get("eng", {}).get("summary") else "fra"

        return {
            "_id": raw.get("referenceCode") or raw.get("id", ""),
            "_source": "INTL/CODICES",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("_title", ""),
            "text": raw.get("_text", ""),
            "date": raw.get("_date"),
            "url": f"https://codices.coe.int/codices/documents/precis/{raw.get('id', '')}?lang=eng",
            "reference_code": raw.get("referenceCode", ""),
            "court": raw.get("_court", ""),
            "country": raw.get("_country", ""),
            "language": lang,
            "thesaurus": thesaurus_labels,
        }

    def _fetch_and_enrich(self, search_hit: dict) -> Optional[dict]:
        """Fetch full précis for a search hit and enrich with extracted fields."""
        guid = search_hit.get("id", "")
        if not guid:
            return None

        try:
            precis = self._get_precis(guid)
        except requests.HTTPError as e:
            logger.warning(f"Failed to fetch précis {guid}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching précis {guid}: {e}")
            return None

        text = self._extract_text(precis)
        if not text:
            logger.warning(f"No text for précis {guid}")
            return None

        # Attach extracted fields prefixed with _ for normalize()
        precis["_text"] = text
        precis["_title"] = self._extract_title(precis)
        precis["_date"] = self._extract_date(precis)
        precis["_court"] = self._extract_court(precis)
        precis["_country"] = self._extract_country(precis)

        return precis

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all précis with full text."""
        page = 0
        total_yielded = 0

        while True:
            logger.info(f"Searching page {page} (yielded {total_yielded} so far)")
            try:
                results = self._search(page=page)
            except requests.HTTPError as e:
                logger.error(f"Search failed on page {page}: {e}")
                break

            hits = results.get("searchResult", [])
            has_more = results.get("hasMoreChildren", False)
            if not hits:
                logger.info(f"No results on page {page}, done")
                break

            logger.info(f"Page {page}: {len(hits)} results")

            for hit in hits:
                enriched = self._fetch_and_enrich(hit)
                if enriched:
                    yield enriched
                    total_yielded += 1
                time.sleep(1.0)

            if not has_more:
                logger.info("No more pages, done")
                break

            page += 1
            time.sleep(0.5)

        logger.info(f"fetch_all complete: {total_yielded} documents")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Yield précis newer than `since` (ISO date string)."""
        page = 0
        total_yielded = 0

        while page < 20:
            logger.info(f"Update search page {page}")
            try:
                results = self._search(page=page, StartDate=since)
            except requests.HTTPError as e:
                logger.error(f"Update search failed: {e}")
                break

            hits = results.get("searchResult", [])
            has_more = results.get("hasMoreChildren", False)
            if not hits:
                break

            for hit in hits:
                enriched = self._fetch_and_enrich(hit)
                if enriched:
                    yield enriched
                    total_yielded += 1
                time.sleep(1.0)

            if not has_more:
                break
            page += 1
            time.sleep(0.5)

        logger.info(f"fetch_updates complete: {total_yielded} documents since {since}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="INTL/CODICES -- Venice Commission Constitutional Case Law"
    )
    subparsers = parser.add_subparsers(dest="command")

    bp = subparsers.add_parser("bootstrap", help="Full initial fetch")
    bp.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    bp.add_argument("--sample-size", type=int, default=15, help="Sample size")
    bp.add_argument("--full", action="store_true", help="Fetch all records")

    subparsers.add_parser("update", help="Incremental update")
    subparsers.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scraper = CODICESScraper()

    if args.command == "test":
        logger.info("Testing CODICES API connectivity...")
        try:
            results = scraper._search(page=0, Size=3)
            hits = results.get("searchResult", [])
            logger.info(f"Search OK: {len(hits)} results returned")

            if hits:
                guid = hits[0]["id"]
                logger.info(f"Fetching précis {guid}...")
                precis = scraper._get_precis(guid)
                text = scraper._extract_text(precis)
                title = scraper._extract_title(precis)
                logger.info(f"Title: {title}")
                logger.info(f"Text length: {len(text)} chars")
                logger.info(f"Preview: {text[:200]}")
                logger.info("Connectivity test passed!")
            else:
                logger.warning("No results found")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            sys.exit(1)

    elif args.command == "bootstrap":
        stats = scraper.bootstrap(
            sample_mode=args.sample,
            sample_size=args.sample_size,
        )
        logger.info(f"Bootstrap complete: {json.dumps(stats, indent=2)}")

    elif args.command == "update":
        stats = scraper.update()
        logger.info(f"Update complete: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
