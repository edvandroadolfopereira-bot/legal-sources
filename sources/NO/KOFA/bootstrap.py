#!/usr/bin/env python3
"""
NO/KOFA - Norwegian Public Procurement Complaints Board Fetcher

Fetches KOFA decisions from klagenemndssekretariatet.no.
~4,900 procurement dispute decisions from 2003-present.

Data access strategy:
  1. WP REST API for case listing + pagination (/wp-json/wp/v2/sak)
  2. HTML scraping of case pages for metadata + PDF links
  3. PDF download + text extraction for full decision text

License: NLOD 2.0 (Norwegian License for Open Government Data)
"""

import argparse
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import logging
import requests

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NO.KOFA")

BASE_URL = "https://www.klagenemndssekretariatet.no"
API_URL = f"{BASE_URL}/wp-json/wp/v2/sak"
SAMPLE_DIR = Path(__file__).parent / "sample"
CHECKPOINT_FILE = Path(__file__).parent / "checkpoint.json"
SOURCE_ID = "NO/KOFA"

PER_PAGE = 50


class KOFAScraper(BaseScraper):
    """Scraper for NO/KOFA — Norwegian Public Procurement Complaints Board."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json,text/html,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5,nb;q=0.3",
        })

    def _load_checkpoint(self) -> dict:
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        return {'last_page': 0, 'fetched_ids': []}

    def _save_checkpoint(self, checkpoint: dict):
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint, f, indent=2)

    @staticmethod
    def _parse_no_date(date_str: str) -> Optional[str]:
        """Parse Norwegian date format dd.mm.yyyy to ISO yyyy-mm-dd."""
        if not date_str:
            return None
        m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str.strip())
        if m:
            return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
        return None

    def _fetch_api_page(self, page: int) -> tuple:
        """Fetch a page of cases from the WP REST API.
        Returns (cases_list, total_cases, total_pages).
        """
        url = f"{API_URL}?per_page={PER_PAGE}&page={page}&orderby=date&order=asc"
        logger.info(f"Fetching API page {page}")
        time.sleep(1)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("X-WP-Total", 0))
        total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
        return resp.json(), total, total_pages

    def _parse_case_html(self, url: str) -> dict:
        """Scrape a case detail page for metadata and PDF link."""
        time.sleep(1)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text

        metadata = {}

        # Extract PDF link
        pdf_match = re.search(r'href="([^"]*\.pdf[^"]*)"', html)
        if pdf_match:
            metadata['pdf_url'] = pdf_match.group(1)

        # Extract metadata from tables (td+td layout, not th+td)
        if BeautifulSoup:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table', class_='table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    tds = row.find_all('td')
                    if len(tds) >= 2:
                        key = tds[0].get_text(strip=True).rstrip(':')
                        val = tds[1].get_text(strip=True)
                        if key and val:
                            metadata[key] = val

            # Extract summary from contentcase div
            content_div = soup.find('div', class_='contentcase')
            if content_div:
                metadata['summary'] = content_div.get_text(strip=True)
        else:
            # Fallback regex parsing
            table_rows = re.findall(
                r'<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
                html, re.DOTALL
            )
            for label, val in table_rows:
                label = re.sub(r'<[^>]+>', '', label).strip()
                val = re.sub(r'<[^>]+>', '', val).strip()
                if label and val:
                    metadata[label] = val

            m = re.search(r'<div class="contentcase">(.*?)</div>', html, re.DOTALL)
            if m:
                metadata['summary'] = re.sub(r'<[^>]+>', '', m.group(1)).strip()

        return metadata

    def _extract_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract text."""
        if not pypdf:
            logger.warning("pypdf not available, cannot extract PDF text")
            return None

        try:
            time.sleep(1)
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()

            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            text = "\n".join(text_parts).strip()
            if text:
                return text
        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")
        return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all KOFA decisions with full text."""
        checkpoint = self._load_checkpoint()
        start_page = checkpoint.get('last_page', 0) + 1
        fetched_ids = set(checkpoint.get('fetched_ids', []))

        page = start_page
        total_pages = None

        while True:
            try:
                cases, total, tp = self._fetch_api_page(page)
            except requests.RequestException as e:
                logger.error(f"API request failed on page {page}: {e}")
                break

            if total_pages is None:
                total_pages = tp
                logger.info(f"Total cases: {total}, pages: {total_pages}")

            if not cases:
                break

            for case in cases:
                case_id = case.get('id')
                if case_id in fetched_ids:
                    continue

                slug = case.get('slug', '')
                case_url = case.get('link', f"{BASE_URL}/sak/{slug}")
                title = case.get('title', {}).get('rendered', slug)
                api_content = case.get('content', {}).get('rendered', '')
                api_content = re.sub(r'<[^>]+>', '', api_content).strip()
                wp_date = case.get('date', '')

                # Scrape HTML page for metadata and PDF link
                try:
                    html_meta = self._parse_case_html(case_url)
                except Exception as e:
                    logger.warning(f"Failed to scrape {case_url}: {e}")
                    html_meta = {}

                # Extract full text from PDF
                full_text = None
                pdf_url = html_meta.get('pdf_url')
                if pdf_url:
                    full_text = self._extract_pdf_text(pdf_url)

                # Use summary as fallback if no PDF text
                if not full_text:
                    summary = html_meta.get('summary', api_content)
                    if summary and len(summary) > 100:
                        full_text = summary
                    else:
                        full_text = api_content

                # Prefer closing date from metadata over WP date
                decision_date = self._parse_no_date(
                    html_meta.get('Avsluttet', '')
                ) or wp_date[:10] if wp_date else None

                record = {
                    '_id': f"KOFA-{slug}",
                    '_source': SOURCE_ID,
                    '_type': 'case_law',
                    '_fetched_at': datetime.now(timezone.utc).isoformat(),
                    'case_number': title,
                    'title': f"KOFA {title}",
                    'text': full_text,
                    'date': decision_date,
                    'url': case_url,
                    'pdf_url': pdf_url,
                    'defendant': html_meta.get('Innklaget', ''),
                    'claimant': html_meta.get('Klager', ''),
                    'decision': html_meta.get('Avgjørelse', html_meta.get('Vedtak', '')),
                    'case_type': html_meta.get('Type sak', ''),
                    'subject': html_meta.get('Saken gjelder', ''),
                    'competition_form': html_meta.get('Konkurranseform', ''),
                    'legal_framework': html_meta.get('Regelverk', ''),
                    'case_handler': html_meta.get('Saksbehandler', ''),
                    'registration_date': html_meta.get('Registrert inn', ''),
                    'closing_date': html_meta.get('Avsluttet', ''),
                    'decided_by': html_meta.get('Avgjort av', ''),
                    'status': html_meta.get('Status', ''),
                }

                yield record
                fetched_ids.add(case_id)

            # Save checkpoint after each page
            checkpoint = {
                'last_page': page,
                'fetched_ids': list(fetched_ids),
            }
            self._save_checkpoint(checkpoint)

            if page >= (total_pages or 1):
                break
            page += 1

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Yield cases modified since a date."""
        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        page = 1

        while True:
            try:
                cases, total, total_pages = self._fetch_api_page(page)
            except requests.RequestException as e:
                logger.error(f"API request failed: {e}")
                break

            if not cases:
                break

            found_old = False
            for case in cases:
                mod_date = case.get('modified', '')
                if mod_date:
                    try:
                        mod_dt = datetime.fromisoformat(mod_date)
                        if mod_dt.tzinfo is None:
                            mod_dt = mod_dt.replace(tzinfo=timezone.utc)
                        if mod_dt < since_dt:
                            found_old = True
                            continue
                    except ValueError:
                        pass

                slug = case.get('slug', '')
                case_url = case.get('link', f"{BASE_URL}/sak/{slug}")
                title = case.get('title', {}).get('rendered', slug)
                api_content = case.get('content', {}).get('rendered', '')
                api_content = re.sub(r'<[^>]+>', '', api_content).strip()

                try:
                    html_meta = self._parse_case_html(case_url)
                except Exception:
                    html_meta = {}

                full_text = None
                pdf_url = html_meta.get('pdf_url')
                if pdf_url:
                    full_text = self._extract_pdf_text(pdf_url)
                if not full_text:
                    full_text = html_meta.get('summary', api_content)

                yield {
                    '_id': f"KOFA-{slug}",
                    '_source': SOURCE_ID,
                    '_type': 'case_law',
                    '_fetched_at': datetime.now(timezone.utc).isoformat(),
                    'case_number': title,
                    'title': f"KOFA {title}",
                    'text': full_text,
                    'date': case.get('date', '')[:10],
                    'url': case_url,
                    'pdf_url': pdf_url,
                }

            if page >= (total_pages or 1):
                break
            page += 1

    def normalize(self, raw: dict) -> dict:
        """Normalize a raw record to the standard schema."""
        return {
            '_id': raw.get('_id', ''),
            '_source': SOURCE_ID,
            '_type': 'case_law',
            '_fetched_at': raw.get('_fetched_at', datetime.now(timezone.utc).isoformat()),
            'title': raw.get('title', ''),
            'text': raw.get('text', ''),
            'date': raw.get('date'),
            'url': raw.get('url', ''),
            'case_number': raw.get('case_number', ''),
            'pdf_url': raw.get('pdf_url', ''),
            'defendant': raw.get('defendant', ''),
            'claimant': raw.get('claimant', ''),
            'decision': raw.get('decision', ''),
            'case_type': raw.get('case_type', ''),
            'subject': raw.get('subject', ''),
            'competition_form': raw.get('competition_form', ''),
            'legal_framework': raw.get('legal_framework', ''),
        }


def bootstrap(sample: bool = False):
    """Bootstrap the NO/KOFA data source."""
    scraper = KOFAScraper()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    max_records = 15 if sample else float('inf')

    for record in scraper.fetch_all():
        normalized = scraper.normalize(record)

        if sample:
            out_file = SAMPLE_DIR / f"{normalized['_id']}.json"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            text_len = len(normalized.get('text', '') or '')
            logger.info(
                f"[{count + 1}] {normalized['_id']} — "
                f"{text_len} chars text, date={normalized.get('date')}"
            )

        count += 1
        if count >= max_records:
            break

    logger.info(f"Done. {count} records {'sampled' if sample else 'fetched'}.")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NO/KOFA bootstrap")
    parser.add_argument("action", choices=["bootstrap"], help="Action to perform")
    parser.add_argument("--sample", action="store_true", help="Fetch sample only (15 records)")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    if args.action == "bootstrap":
        bootstrap(sample=args.sample or not args.full)
