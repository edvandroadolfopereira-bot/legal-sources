#!/usr/bin/env python3
"""
EU/EPPO — European Public Prosecutor's Office Case Information

Fetches case press releases from the EPPO website. These cover investigations,
indictments, seizures, and convictions for crimes against the EU budget
(VAT fraud, subsidy fraud, corruption, money laundering).

Source: https://www.eppo.europa.eu/en/news
Access: HTML scraping of paginated news listing + individual article pages
Auth: None required
~870+ articles since EPPO's operational start in June 2021
"""

import argparse
import html as html_mod
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_ID = "EU/EPPO"
BASE_URL = "https://www.eppo.europa.eu"
NEWS_PATH = "/en/news"


class EPPOFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def _request(self, url: str, timeout: int = 60, retries: int = 3) -> Optional[requests.Response]:
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed ({attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def _extract_article_links(self, html: str) -> List[str]:
        """Extract article slugs from a news listing page."""
        links = re.findall(r'href="(/en/media/news/[^"]+)"', html)
        return list(dict.fromkeys(links))  # dedupe, preserve order

    def _parse_article(self, url: str, html: str) -> Optional[Dict[str, Any]]:
        """Parse an individual article page for title, date, and full text."""
        soup = BeautifulSoup(html, 'html.parser')

        # Title
        title_el = soup.find('h1') or soup.find('title')
        title = title_el.get_text(strip=True) if title_el else ''
        # Clean " | European Public Prosecutor's Office" suffix
        title = re.sub(r'\s*\|\s*European Public Prosecutor.*$', '', title).strip()
        if not title:
            return None

        # Date — look for datetime attribute
        date = None
        time_el = soup.find('time', attrs={'datetime': True})
        if time_el:
            dt_str = time_el['datetime']
            try:
                date = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                pass
        if not date:
            # Fallback: parse from text like "(Luxembourg, 8 June 2026)"
            m = re.search(r'\(Luxembourg,?\s*(\d{1,2}\s+\w+\s+\d{4})\)', html)
            if m:
                for fmt in ['%d %B %Y', '%d %b %Y']:
                    try:
                        date = datetime.strptime(m.group(1).strip(), fmt).strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue

        # Full text — extract from <main> or fall back to all <p> tags
        main_el = soup.find('main')
        container = main_el if main_el else soup

        paragraphs = container.find_all('p')
        text_parts = []
        for p in paragraphs:
            t = p.get_text(separator=' ', strip=True)
            # Skip boilerplate
            if t.lower().startswith('share this page'):
                continue
            if t.lower().startswith('cookie') or 'accept cookies' in t.lower():
                continue
            if len(t) > 10:
                text_parts.append(t)

        text = '\n\n'.join(text_parts)
        # Clean entities and extra whitespace
        text = html_mod.unescape(text)
        text = re.sub(r'\xa0', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # Extract slug for ID
        slug = url.rstrip('/').split('/')[-1]

        return {
            'slug': slug,
            'title': title,
            'date': date,
            'text': text,
            'url': url,
        }

    def fetch_all(self, max_docs: int = None) -> Iterator[Dict[str, Any]]:
        """Fetch all EPPO news articles with full text."""
        page = 0
        fetched = 0
        consecutive_empty = 0

        while True:
            if max_docs and fetched >= max_docs:
                return

            url = f"{BASE_URL}{NEWS_PATH}?page={page}"
            logger.info(f"Fetching listing page {page}...")

            resp = self._request(url)
            if not resp:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                page += 1
                continue

            links = self._extract_article_links(resp.text)
            if not links:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    logger.info(f"No more articles (page {page})")
                    break
                page += 1
                continue

            consecutive_empty = 0

            for link in links:
                if max_docs and fetched >= max_docs:
                    return

                article_url = BASE_URL + link
                time.sleep(1.5)

                art_resp = self._request(article_url)
                if not art_resp:
                    logger.warning(f"Failed to fetch article: {article_url}")
                    continue

                parsed = self._parse_article(article_url, art_resp.text)
                if parsed:
                    yield parsed
                    fetched += 1

            page += 1
            time.sleep(2.0)

        logger.info(f"Total fetched: {fetched}")

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize to standard schema."""
        return {
            '_id': raw['slug'],
            '_source': SOURCE_ID,
            '_type': 'case_law',
            '_fetched_at': datetime.utcnow().isoformat(),
            'title': raw['title'],
            'text': raw.get('text', ''),
            'date': raw.get('date'),
            'url': raw['url'],
        }


def main():
    parser = argparse.ArgumentParser(description='EU/EPPO case information fetcher')
    parser.add_argument('command', choices=['bootstrap', 'bootstrap-fast'])
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()

    fetcher = EPPOFetcher()
    sample_dir = Path(__file__).parent / 'sample'
    sample_dir.mkdir(exist_ok=True)

    target = 15 if args.sample or not args.full else None
    max_docs = target * 2 if target else None
    logger.info(f"Fetching {'sample (target ' + str(target) + ')' if target else 'ALL'} articles...")

    count = 0
    skipped = 0

    for raw in fetcher.fetch_all(max_docs=max_docs):
        normalized = fetcher.normalize(raw)

        if len(normalized.get('text', '')) < 100:
            skipped += 1
            logger.warning(f"Skipped {normalized['_id']} — insufficient text ({len(normalized.get('text', ''))} chars)")
            continue

        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', normalized['_id'])[:120] + '.json'
        filepath = sample_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)

        count += 1
        logger.info(f"[{count}] {normalized['_id']} — {len(normalized['text']):,} chars")

        if target and count >= target:
            break

    logger.info(f"Done. Saved {count}, skipped {skipped} (insufficient text).")

    if count > 0:
        files = list(sample_dir.glob('*.json'))
        total_chars = sum(len(json.load(open(f)).get('text', '')) for f in files)
        avg = total_chars // len(files) if files else 0
        logger.info(f"Average: {avg:,} chars/doc across {len(files)} files")


if __name__ == '__main__':
    main()
