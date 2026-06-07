#!/usr/bin/env python3
"""
INTL/INCADAT -- International Child Abduction Case Law Database

Fetches case law from INCADAT (incadat.com), maintained by the Hague
Conference on Private International Law (HCCH). Contains ~1700 leading
judicial decisions on the 1980 Child Abduction Convention from 60+ countries.

Approach:
  1. Iterate through case IDs (2–1711)
  2. Fetch each case page /en/case/<ID>
  3. Parse metadata + summary (facts, ruling, grounds commentary)
  4. Full text = facts + ruling + grounds (rich legal analysis)

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
logger = logging.getLogger("legal-data-hunter.INTL.INCADAT")

SOURCE_ID = "INTL/INCADAT"
SAMPLE_DIR = Path(__file__).parent / "sample"
BASE_URL = "https://www.incadat.com"

HEADERS = {
    "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DELAY = 2.0

# ID range for INCADAT cases (ID 1 is 404, IDs 2-1711 are valid)
MIN_ID = 2
MAX_ID = 1711


def clean_html(text: str) -> str:
    """Strip HTML tags and clean text."""
    if not text:
        return ""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_mod.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_meta(html: str, label: str) -> str:
    """Extract metadata value from a meta-label + following <p> or text."""
    pattern = (
        rf'<div class="meta-label">{re.escape(label)}</div>'
        r'\s*</div>\s*<div[^>]*>\s*<p>(.*?)</p>'
    )
    m = re.search(pattern, html, re.DOTALL)
    if m:
        return clean_html(m.group(1)).strip()
    # Try without <p> wrapper
    pattern2 = (
        rf'<div class="meta-label">{re.escape(label)}</div>'
        r'\s*</div>\s*<div[^>]*>(.*?)</div>'
    )
    m2 = re.search(pattern2, html, re.DOTALL)
    if m2:
        return clean_html(m2.group(1)).strip()
    return ""


def _extract_section(html: str, heading: str) -> str:
    """Extract a summary section (Facts, Ruling, Grounds) by heading."""
    pattern = (
        rf'<h3>{re.escape(heading)}</h3>'
        r'\s*</div>\s*</div>\s*<div[^>]*>\s*<article[^>]*>(.*?)</article>'
    )
    m = re.search(pattern, html, re.DOTALL)
    if m:
        return clean_html(m.group(1)).strip()
    return ""


def _extract_grounds_section(html: str) -> str:
    """Extract the Grounds section which may have sub-headings."""
    # Grounds section starts with <h3>Grounds</h3> and contains article content
    pattern = (
        r'<h3>Grounds</h3>'
        r'\s*</div>\s*</div>\s*<div[^>]*>\s*<article[^>]*>(.*?)</article>'
    )
    m = re.search(pattern, html, re.DOTALL)
    if m:
        return clean_html(m.group(1)).strip()
    return ""


def _extract_articles(html: str, label: str) -> list:
    """Extract article references (e.g., HC articles Considered)."""
    pattern = (
        rf'<div class="meta-label">{re.escape(label)}</div>'
        r'.*?<div class="meta articles">(.*?)</div>\s*</div>'
    )
    m = re.search(pattern, html, re.DOTALL)
    if m:
        spans = re.findall(r'<span[^>]*>(.*?)</span>', m.group(1))
        return [clean_html(s).strip() for s in spans if clean_html(s).strip()]
    return []


class INCADATScraper(BaseScraper):
    """Scraper for INTL/INCADAT — International Child Abduction Case Law."""

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
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.text
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                wait = 5 * (attempt + 1)
                logger.warning(f"Attempt {attempt+1}/3 failed for {url}: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    wait = 30 * (attempt + 1)
                    logger.warning(f"Rate limited on {url}. Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"HTTP error for {url}: {e}")
                    return None
        logger.error(f"All retries exhausted for {url}")
        return None

    def _parse_case(self, case_id: int, html: str) -> Optional[dict]:
        """Parse a case page HTML into a raw record."""
        # Case title
        title_m = re.search(r'<h3 class="case-title[^"]*">(.*?)</h3>', html, re.DOTALL)
        title = clean_html(title_m.group(1)).strip() if title_m else ""

        # INCADAT reference
        ref_m = re.search(r'<h3>INCADAT reference</h3>.*?<p class="p-large">(.*?)</p>', html, re.DOTALL)
        incadat_ref = clean_html(ref_m.group(1)).strip() if ref_m else ""

        # Court metadata
        country = _extract_meta(html, "Country")
        court_name = _extract_meta(html, "Name")
        court_level = _extract_meta(html, "Level")
        judges = _extract_meta(html, "Judge(s)")

        # States involved
        requesting_state = _extract_meta(html, "Requesting State")
        requested_state = _extract_meta(html, "Requested State")

        # Decision metadata
        date_str = _extract_meta(html, "Date")
        status = _extract_meta(html, "Status")
        grounds_meta = _extract_meta(html, "Grounds")
        order = _extract_meta(html, "Order")

        # Articles
        articles_considered = _extract_articles(html, "HC article(s) Considered")
        articles_relied = _extract_articles(html, "HC article(s) Relied Upon")

        # Authorities
        auth_m = re.search(
            r'<div class="meta-label">Authorities \| Cases referred to</div>'
            r'.*?<div class="referrals">(.*?)</div>',
            html, re.DOTALL
        )
        authorities = clean_html(auth_m.group(1)).strip() if auth_m else ""

        # Published in
        pub_m = re.search(r'<div class="meta-label">Published in</div>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
        published_in = clean_html(pub_m.group(1)).strip() if pub_m else ""

        # Full text download URL
        dl_m = re.search(r'href="(/download/[^"]+)"', html)
        full_text_url = f"{BASE_URL}{dl_m.group(1)}" if dl_m else ""

        # Summary sections (EN tab)
        en_tab_m = re.search(
            r'<div class="summlangtab" data-summlangtab="en">(.*?)(?:<div class="summlangtab"|</div>\s*</div>\s*</div>\s*<!-- )',
            html, re.DOTALL
        )
        en_tab = en_tab_m.group(1) if en_tab_m else html

        facts = _extract_section(en_tab, "Facts")
        ruling = _extract_section(en_tab, "Ruling")
        grounds = _extract_grounds_section(en_tab)

        # INCADAT commentary
        comment_m = re.search(
            r'<h3>INCADAT comment.*?</h3>.*?</div>\s*</div>\s*<div[^>]*>\s*<article[^>]*>(.*?)</article>',
            html, re.DOTALL
        )
        commentary = clean_html(comment_m.group(1)).strip() if comment_m else ""

        # Parse date
        parsed_date = None
        if date_str:
            date_clean = re.sub(r'^\s+', '', date_str)
            for fmt in ("%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed_date = datetime.strptime(date_clean, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

        # Build full text from summary sections
        text_parts = []
        if facts:
            text_parts.append(f"FACTS\n\n{facts}")
        if ruling:
            text_parts.append(f"RULING\n\n{ruling}")
        if grounds:
            text_parts.append(f"GROUNDS\n\n{grounds}")
        if commentary:
            text_parts.append(f"INCADAT COMMENTARY\n\n{commentary}")
        full_text = "\n\n---\n\n".join(text_parts)

        if not title and not full_text:
            return None

        return {
            "case_id": case_id,
            "title": title,
            "incadat_ref": incadat_ref,
            "country": country,
            "court_name": court_name,
            "court_level": court_level,
            "judges": judges,
            "requesting_state": requesting_state,
            "requested_state": requested_state,
            "date": parsed_date,
            "date_raw": date_str,
            "status": status,
            "grounds_label": grounds_meta,
            "order": order,
            "articles_considered": articles_considered,
            "articles_relied": articles_relied,
            "authorities": authorities,
            "published_in": published_in,
            "full_text_url": full_text_url,
            "facts": facts,
            "ruling": ruling,
            "grounds": grounds,
            "commentary": commentary,
            "text": full_text,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Iterate through all case IDs and yield parsed records."""
        for case_id in range(MIN_ID, MAX_ID + 1):
            url = f"{BASE_URL}/en/case/{case_id}"
            html = self._get(url)
            if html is None:
                logger.debug(f"Case {case_id}: not found or error, skipping")
                continue
            record = self._parse_case(case_id, html)
            if record:
                logger.info(f"Case {case_id}: {record['title'][:60]}...")
                yield record
            else:
                logger.debug(f"Case {case_id}: no parseable content")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """INCADAT has no date-filtered endpoint; re-scan recent IDs."""
        for case_id in range(max(MIN_ID, MAX_ID - 50), MAX_ID + 1):
            url = f"{BASE_URL}/en/case/{case_id}"
            html = self._get(url)
            if html is None:
                continue
            record = self._parse_case(case_id, html)
            if record and record.get("date"):
                try:
                    d = datetime.strptime(record["date"], "%Y-%m-%d")
                    if d >= since.replace(tzinfo=None):
                        yield record
                except ValueError:
                    yield record

    def normalize(self, raw: dict) -> dict:
        """Transform raw record into standard schema."""
        return {
            "_id": f"INCADAT-{raw['case_id']}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "url": f"{BASE_URL}/en/case/{raw['case_id']}",
            "incadat_ref": raw.get("incadat_ref", ""),
            "country": raw.get("country", ""),
            "court": raw.get("court_name", ""),
            "court_level": raw.get("court_level", ""),
            "judges": raw.get("judges", ""),
            "requesting_state": raw.get("requesting_state", ""),
            "requested_state": raw.get("requested_state", ""),
            "decision_status": raw.get("status", ""),
            "grounds": raw.get("grounds_label", ""),
            "order": raw.get("order", ""),
            "articles_considered": raw.get("articles_considered", []),
            "articles_relied": raw.get("articles_relied", []),
            "authorities": raw.get("authorities", ""),
            "full_text_url": raw.get("full_text_url", ""),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="INTL/INCADAT scraper")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "test"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Sample mode: fetch 15 records only")
    parser.add_argument("--full", action="store_true",
                        help="Full mode (default for bootstrap)")
    args = parser.parse_args()

    scraper = INCADATScraper()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "test":
        url = f"{BASE_URL}/en/case/469"
        html = scraper._get(url)
        if html:
            record = scraper._parse_case(469, html)
            if record:
                normalized = scraper.normalize(record)
                print(json.dumps(normalized, indent=2, ensure_ascii=False, default=str))
                print(f"\nText length: {len(normalized.get('text', ''))}")
                return
        print("ERROR: Could not fetch test case")
        sys.exit(1)

    sample_mode = args.sample or args.command == "test"
    limit = 15 if sample_mode else None
    count = 0

    for raw in scraper.fetch_all():
        normalized = scraper.normalize(raw)
        text_len = len(normalized.get("text", ""))
        if text_len < 100:
            logger.warning(f"Skipping {normalized['_id']}: insufficient text ({text_len} chars)")
            continue

        # Save sample
        sample_path = SAMPLE_DIR / f"{normalized['_id'].replace('/', '_')}.json"
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False, default=str)

        count += 1
        logger.info(f"[{count}] {normalized['_id']}: {normalized['title'][:50]}... ({text_len} chars)")

        if limit and count >= limit:
            break

    logger.info(f"Done. {count} records saved to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
