#!/usr/bin/env python3
"""
INTL/Juricaf -- Francophone Supreme Court Decisions

Fetches supreme court decisions from juricaf.org, the AHJUCAF database of
francophone judicial decisions covering 48 countries/institutions.

Strategy:
  - Paginate search results by country: /recherche/+/facet_pays:{COUNTRY}?page=N
  - Extract decision links from search results (/arret/{ID} pattern)
  - Fetch each decision page and extract full text from <article> tag
  - Parse metadata from header (date, court, case number)

Data Coverage:
  - ~1.86M decisions from 48 francophone jurisdictions
  - Supreme/cassation courts of France, Belgium, Luxembourg, Switzerland,
    Canada, Monaco, Senegal, Madagascar, Benin, Mali, Niger, etc.
  - International courts: OHADA, UEMOA, CEMAC, ECOWAS, ECHR, CJEU

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py update             # Incremental update
"""

import sys
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional
from html import unescape

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.Juricaf")

BASE_URL = "https://juricaf.org"

# Countries available on Juricaf with their URL-encoded names
# Only include countries with >5 decisions for efficiency
JURICAF_COUNTRIES = [
    "France", "Suisse", "Luxembourg", "Sénégal", "Belgique",
    "Canada", "Monaco", "Bénin", "Madagascar", "Maroc",
    "OHADA", "CEDH", "CJUE", "Mali", "Niger",
    "Tchad", "Cameroun", "Burkina_Faso", "Togo", "CEDEAO",
    "Côte_d'Ivoire", "Congo", "Guinée", "CEMAC", "Haïti",
    "Congo_démocratique", "Bulgarie", "Mauritanie", "Gabon",
    "République_centrafricaine", "République_Tchèque", "Roumanie",
    "Liban", "Tunisie", "Cambodge", "Burundi", "UEMOA",
    "Comores", "Andorre",
]

# Map Juricaf country names to our ISO codes
COUNTRY_MAP = {
    "France": "FR", "Suisse": "CH", "Luxembourg": "LU",
    "Sénégal": "SN", "Belgique": "BE", "Canada": "CA",
    "Monaco": "MC", "Bénin": "BJ", "Madagascar": "MG",
    "Maroc": "MA", "Mali": "ML", "Niger": "NE",
    "Tchad": "TD", "Cameroun": "CM", "Burkina_Faso": "BF",
    "Togo": "TG", "Côte_d'Ivoire": "CI", "Congo": "CG",
    "Guinée": "GN", "Haïti": "HT", "Congo_démocratique": "CD",
    "Bulgarie": "BG", "Mauritanie": "MR", "Gabon": "GA",
    "République_centrafricaine": "CF", "République_Tchèque": "CZ",
    "Roumanie": "RO", "Liban": "LB", "Tunisie": "TN",
    "Cambodge": "KH", "Burundi": "BI", "Comores": "KM",
    "Andorre": "AD",
    # International courts
    "OHADA": "INTL", "CEDH": "CoE", "CJUE": "EU",
    "CEDEAO": "INTL", "CEMAC": "INTL", "UEMOA": "INTL",
}

# For sample mode, use smaller countries
SAMPLE_COUNTRIES = ["Burundi", "Comores", "Andorre", "Mauritanie", "UEMOA"]


class JuricafScraper(BaseScraper):
    """Scraper for Juricaf francophone supreme court decisions."""

    def __init__(self, source_dir: str = None, sample_mode: bool = False):
        if source_dir is None:
            source_dir = str(Path(__file__).parent)
        super().__init__(source_dir)
        self._sample_mode = sample_mode
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; +https://github.com/worldwidelaw/legal-sources)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr,en",
        })

    def _search_country(self, country: str, max_pages: int = None) -> list[str]:
        """Get all decision URLs for a country by paginating search results."""
        encoded = urllib.parse.quote(country, safe='')
        decision_urls = []
        page = 1

        while True:
            url = f"{BASE_URL}/recherche/+/facet_pays:{encoded}"
            params = {"tri": "DESC", "pays": country, "page": page}
            time.sleep(1.5)

            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"  Page {page} returned {resp.status_code}")
                    break
            except requests.RequestException as e:
                logger.error(f"  Error fetching page {page}: {e}")
                break

            # Extract decision links
            links = re.findall(r'href="(/arret/[^"]+)"', resp.text)
            if not links:
                break

            for link in links:
                full_url = f"{BASE_URL}{link}"
                if full_url not in decision_urls:
                    decision_urls.append(full_url)

            logger.info(f"  {country} page {page}: {len(links)} links (total {len(decision_urls)})")

            # Check for next page
            if f"page={page + 1}" not in resp.text:
                break

            if max_pages and page >= max_pages:
                break

            page += 1

        return decision_urls

    def _fetch_decision(self, url: str) -> Optional[dict]:
        """Fetch and parse a single decision page."""
        time.sleep(1)
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
        except requests.RequestException as e:
            logger.error(f"  Error fetching {url}: {e}")
            return None

        html = resp.text

        # Extract title from h1
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        title = ""
        if h1:
            title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
            title = re.sub(r'^\|\s*', '', title).strip()

        # Extract full text from <article>
        article = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
        text = ""
        if article:
            text = re.sub(r'<[^>]+>', '', article.group(1))
            text = unescape(text).strip()
            # Clean up excessive whitespace but preserve paragraph breaks
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.strip()

        # Parse URL slug for metadata
        slug = url.split("/arret/")[-1] if "/arret/" in url else ""
        parts = slug.split("-") if slug else []

        # Extract date from header metadata
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', html)
        date_str = None
        if date_match:
            try:
                dt = datetime.strptime(date_match.group(1), "%d/%m/%Y")
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Fallback: extract date from slug (format: YYYYMMDD)
        if not date_str and len(parts) >= 3:
            date_part = parts[-2] if len(parts[-2]) == 8 else None
            if not date_part:
                for p in parts:
                    if len(p) == 8 and p.isdigit():
                        date_part = p
                        break
            if date_part and date_part.isdigit():
                try:
                    dt = datetime.strptime(date_part, "%Y%m%d")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # Extract country and court from slug
        country_name = parts[0] if parts else ""
        court_parts = []
        for p in parts[1:]:
            if len(p) == 8 and p.isdigit():
                break
            court_parts.append(p)
        court = " ".join(court_parts) if court_parts else ""

        # Extract case number from header
        case_num_match = re.search(r'N°\s*([^\s<]+)', html)
        case_number = case_num_match.group(1) if case_num_match else (parts[-1] if parts else "")

        # Extract ECLI if present
        ecli_match = re.search(r'(ECLI:[^\s<"]+)', html)
        ecli = ecli_match.group(1) if ecli_match else None

        return {
            "slug": slug,
            "title": title,
            "text": text,
            "date": date_str,
            "court": court,
            "country_origin": country_name,
            "case_number": case_number,
            "ecli": ecli,
            "url": url,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all decisions across all Juricaf countries."""
        countries = SAMPLE_COUNTRIES if self._sample_mode else JURICAF_COUNTRIES
        max_pages = 2 if self._sample_mode else None
        for country in countries:
            logger.info(f"Processing country: {country}")
            urls = self._search_country(country, max_pages=max_pages)
            logger.info(f"  Found {len(urls)} decisions for {country}")

            for i, url in enumerate(urls):
                try:
                    decision = self._fetch_decision(url)
                    if decision and decision.get("text") and len(decision["text"]) > 50:
                        decision["juricaf_country"] = country
                        yield decision
                    else:
                        logger.warning(f"  [{i+1}/{len(urls)}] No text for {url}")
                except Exception as e:
                    logger.error(f"  [{i+1}/{len(urls)}] Error: {e}")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield decisions imported since the given date."""
        # Juricaf doesn't have a date-filtered API, so we fetch recent pages
        for country in JURICAF_COUNTRIES:
            logger.info(f"Checking updates for {country}")
            urls = self._search_country(country, max_pages=2)
            for url in urls:
                try:
                    decision = self._fetch_decision(url)
                    if decision and decision.get("text") and len(decision["text"]) > 50:
                        decision["juricaf_country"] = country
                        yield decision
                except Exception as e:
                    logger.error(f"  Error: {e}")

    def normalize(self, raw: dict) -> dict:
        """Transform raw decision data into standard schema."""
        slug = raw.get("slug", "unknown")
        country_origin = raw.get("country_origin", "")
        iso_code = COUNTRY_MAP.get(raw.get("juricaf_country", ""), "INTL")
        court = raw.get("court", "")

        # Build a readable court name
        court_name = court.replace("COUR", "Cour").replace("SUPREME", "suprême")
        if not court_name:
            court_name = raw.get("juricaf_country", "Unknown Court")

        title = raw.get("title", "")
        if not title:
            title = f"{country_origin} {court} {raw.get('case_number', slug)}"

        return {
            "_id": f"juricaf-{slug}",
            "_source": "INTL/Juricaf",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "url": raw.get("url", ""),
            "court": court_name,
            "country_origin": iso_code,
            "case_number": raw.get("case_number", ""),
            "ecli": raw.get("ecli"),
        }


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv
    scraper = JuricafScraper(sample_mode=sample)

    if command == "test":
        # Quick connectivity test
        urls = scraper._search_country("Burundi", max_pages=1)
        print(f"Found {len(urls)} Burundi decisions on page 1")
        if urls:
            decision = scraper._fetch_decision(urls[0])
            if decision:
                print(f"Title: {decision['title']}")
                print(f"Date: {decision['date']}")
                print(f"Text length: {len(decision.get('text', ''))}")
                print(f"Text preview: {decision.get('text', '')[:200]}...")
        sys.exit(0)

    if command == "bootstrap":
        result = scraper.bootstrap(sample_mode=sample, sample_size=15)
        print(json.dumps(result, indent=2, default=str))
    elif command == "update":
        result = scraper.update()
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
