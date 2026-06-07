#!/usr/bin/env python3
"""
EU/FRA-CaseLaw -- EU Fundamental Rights Agency Case Law Database

Fetches CJEU, ECtHR, and national court cases referencing the EU Charter
of Fundamental Rights from the FRA case law database.

Strategy:
  - Paginate HTML listing (191 pages, ~1,910 cases)
  - Extract case slugs and basic metadata from listing pages
  - Fetch each case detail page for full text (body, charter refs)
  - Normalize into standard schema

Usage:
  python bootstrap.py bootstrap          # Fetch all cases
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
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
logger = logging.getLogger("legal-data-hunter.EU.FRA-CaseLaw")

BASE_URL = "https://fra.europa.eu"
LISTING_URL = f"{BASE_URL}/en/case-law-database"
MAX_PAGES = 191


class FRACaseLawScraper(BaseScraper):
    """Scraper for EU/FRA-CaseLaw -- FRA Case Law Database."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def _request(self, url: str, timeout: int = 60) -> Optional[requests.Response]:
        """HTTP GET with retry and rate limiting."""
        for attempt in range(3):
            try:
                time.sleep(2)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 15s")
                    time.sleep(15)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url[:80]}: {e}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        return None

    def _parse_listing_page(self, html: str) -> List[Dict[str, str]]:
        """Parse a listing page and return case slugs with basic metadata."""
        soup = BeautifulSoup(html, "html.parser")
        cases = []

        links = soup.find_all("a", href=lambda h: h and "/caselaw-reference/" in h)
        seen = set()
        for link in links:
            href = link.get("href", "")
            slug = href.rstrip("/").split("/")[-1] if href else ""
            if not slug or slug in seen:
                continue
            seen.add(slug)

            title = link.get_text(strip=True)
            cases.append({
                "slug": slug,
                "title": title,
                "detail_url": href if href.startswith("http") else BASE_URL + href,
            })

        return cases

    def _extract_field_text(self, soup: BeautifulSoup, field_name: str) -> str:
        """Extract text from a Drupal field div."""
        div = soup.find("div", class_=lambda c: c and field_name in c)
        if not div:
            return ""
        item = div.find("div", class_="field-item") or div.find("div", class_="field-items")
        if item:
            return item.get_text(separator="\n", strip=True)
        return div.get_text(separator="\n", strip=True)

    def _extract_field_link(self, soup: BeautifulSoup, field_name: str) -> str:
        """Extract the first link href from a Drupal field div."""
        div = soup.find("div", class_=lambda c: c and field_name in c)
        if not div:
            return ""
        link = div.find("a")
        return link.get("href", "") if link else ""

    def _extract_charter_articles(self, soup: BeautifulSoup) -> List[str]:
        """Extract charter article references."""
        div = soup.find("div", class_=lambda c: c and "field-name-field-info-charter-article" in c)
        if not div:
            return []
        articles = []
        for item in div.find_all("div", class_="field-item"):
            text = item.get_text(strip=True)
            if text and "Article" in text:
                articles.append(text)
        return articles

    def _parse_date(self, date_str: str) -> str:
        """Parse date like '26/02/2026' or '2 March 2024' to ISO format."""
        date_str = date_str.strip()
        for fmt in ("%d/%m/%Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _fetch_case_detail(self, detail_url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single case detail page."""
        resp = self._request(detail_url)
        if not resp:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._extract_field_text(soup, "field-name-node-title")
        subtitle = self._extract_field_text(soup, "field-name-field-info-subtitle")
        deciding_body_type = self._extract_field_text(soup, "field-name-field-info-deciding-body-type")
        deciding_body = self._extract_field_text(soup, "field-name-field-info-deciding-body")
        case_type = self._extract_field_text(soup, "field-name-field-info-type-of-case-law")
        date_raw = self._extract_field_text(soup, "field-name-field-info-decision-date")
        ecli = self._extract_field_text(soup, "field-name-field-info-ecli")
        external_url = self._extract_field_link(soup, "field-name-field-info-url")
        body = self._extract_field_text(soup, "field-name-field-info-body")

        # Charter articles
        charter_articles = self._extract_charter_articles(soup)

        # Charter paragraphs (reasoning extracts)
        charter_paras_div = soup.find("div", class_=lambda c: c and "field-name-field-info-charter-para" in c)
        charter_paras = ""
        if charter_paras_div:
            charter_paras = charter_paras_div.get_text(separator="\n", strip=True)

        # Build full text from all content fields
        text_parts = []
        if subtitle:
            text_parts.append(f"Parties: {subtitle}")
        if body:
            text_parts.append(body)
        if charter_paras:
            text_parts.append(f"\nCharter Paragraphs:\n{charter_paras}")

        full_text = "\n\n".join(text_parts)

        return {
            "title": title,
            "subtitle": subtitle,
            "deciding_body_type": deciding_body_type,
            "deciding_body": deciding_body,
            "case_type": case_type,
            "date_raw": date_raw,
            "ecli": ecli,
            "external_url": external_url,
            "body": body,
            "charter_articles": charter_articles,
            "charter_paras": charter_paras,
            "text": full_text,
            "detail_url": detail_url,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all cases from the FRA case law database."""
        total_fetched = 0

        for page in range(MAX_PAGES):
            url = f"{LISTING_URL}?page={page}"
            logger.info(f"Fetching listing page {page}/{MAX_PAGES - 1}")

            resp = self._request(url)
            if not resp:
                logger.error(f"Failed to fetch listing page {page}")
                continue

            cases = self._parse_listing_page(resp.text)
            if not cases:
                logger.info(f"No cases found on page {page}, stopping")
                break

            for case_meta in cases:
                detail = self._fetch_case_detail(case_meta["detail_url"])
                if not detail:
                    logger.warning(f"Failed to fetch detail for {case_meta['slug']}")
                    continue

                detail["slug"] = case_meta["slug"]
                total_fetched += 1
                yield detail

                if total_fetched % 50 == 0:
                    logger.info(f"Progress: {total_fetched} cases fetched")

        logger.info(f"Finished: {total_fetched} total cases fetched")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Fetch cases updated since a given date."""
        for record in self.fetch_all():
            date_str = record.get("date_raw", "")
            try:
                date_iso = self._parse_date(date_str)
                record_date = datetime.strptime(date_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if record_date >= since:
                    yield record
            except (ValueError, TypeError):
                yield record

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw case data into standard schema."""
        date_iso = self._parse_date(raw.get("date_raw", ""))
        slug = raw.get("slug", "")
        case_id = f"FRA-{slug}" if slug else f"FRA-{hash(raw.get('title', ''))}"

        return {
            "_id": case_id,
            "_source": "EU/FRA-CaseLaw",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": date_iso,
            "url": raw.get("detail_url", ""),
            "external_url": raw.get("external_url", ""),
            "ecli": raw.get("ecli", ""),
            "deciding_body": raw.get("deciding_body", ""),
            "deciding_body_type": raw.get("deciding_body_type", ""),
            "case_type": raw.get("case_type", ""),
            "parties": raw.get("subtitle", ""),
            "charter_articles": raw.get("charter_articles", []),
        }


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="EU/FRA-CaseLaw bootstrap")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch only 15 samples")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = FRACaseLawScraper()

    if args.command == "test":
        logger.info("Testing connectivity...")
        resp = scraper._request(LISTING_URL)
        if resp and resp.status_code == 200:
            cases = scraper._parse_listing_page(resp.text)
            logger.info(f"OK: listing page returned {len(cases)} cases")
            if cases:
                detail = scraper._fetch_case_detail(cases[0]["detail_url"])
                if detail and detail.get("text"):
                    logger.info(f"OK: detail page has {len(detail['text'])} chars of text")
                else:
                    logger.error("FAIL: could not fetch case detail text")
        else:
            logger.error("FAIL: could not reach listing page")
        return

    # bootstrap or bootstrap-fast
    sample_mode = args.sample
    sample_dir = scraper.source_dir / "sample"
    sample_dir.mkdir(exist_ok=True)

    limit = 15 if sample_mode else None
    count = 0
    records = []

    for raw in scraper.fetch_all():
        normalized = scraper.normalize(raw)
        records.append(normalized)
        count += 1

        if sample_mode:
            sample_path = sample_dir / f"{count:04d}.json"
            with open(sample_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)

        if limit and count >= limit:
            break

    if not sample_mode:
        # Write all records to JSONL
        data_dir = scraper.source_dir / "data"
        data_dir.mkdir(exist_ok=True)
        jsonl_path = data_dir / "fra_caselaw.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info(f"Wrote {count} records to {jsonl_path}")
    else:
        logger.info(f"Wrote {count} sample records to {sample_dir}")

    # Summary
    text_lengths = [len(r.get("text", "")) for r in records]
    avg_text = sum(text_lengths) / len(text_lengths) if text_lengths else 0
    non_empty = sum(1 for t in text_lengths if t > 0)
    logger.info(f"Summary: {count} records, {non_empty}/{count} with text, avg {avg_text:.0f} chars")


if __name__ == "__main__":
    main()
