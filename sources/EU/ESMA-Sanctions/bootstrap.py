#!/usr/bin/env python3
"""
ESMA Sanctions Register — Data Fetcher

Fetches administrative sanctions and measures from ESMA's public Solr-based
Sanctions Register. These are enforcement decisions imposed by EU national
competent authorities (NCAs) under MiFID, MAR, MAD, UCITS, AIFMD, EMIR,
SFTR, BMR, CSDR, and other EU financial legislation.

API: Solr REST endpoint (no auth required)
Format: JSON
Full text: violation descriptions in sn_text field
"""

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_ID = "EU/ESMA-Sanctions"
SOLR_BASE = "https://registers.esma.europa.eu/solr/esma_registers_sanctions/select"
ROWS_PER_PAGE = 500


class ESMASanctionsFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)',
            'Accept': 'application/json',
        })

    def _solr_query(self, start: int = 0, rows: int = ROWS_PER_PAGE) -> Optional[dict]:
        """Query ESMA Sanctions Solr endpoint."""
        params = {
            'q': '*:*',
            'rows': rows,
            'start': start,
            'wt': 'json',
            'sort': 'sn_date desc',
            'fl': '*',
        }
        for attempt in range(3):
            try:
                resp = self.session.get(SOLR_BASE, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Solr query failed (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return None

    def _clean_entity_name(self, raw: str) -> str:
        """Strip HTML anchor tags from entity name field."""
        return re.sub(r'<[^>]+>', '', raw).strip()

    def fetch_all(self, max_docs: int = None) -> Iterator[Dict[str, Any]]:
        """Fetch all sanctions records from the Solr register."""
        start = 0
        fetched = 0

        while True:
            if max_docs and fetched >= max_docs:
                return

            data = self._solr_query(start=start)
            if not data:
                logger.error("Failed to query Solr after retries")
                return

            total = data['response']['numFound']
            docs = data['response']['docs']

            if not docs:
                break

            logger.info(f"Page {start // ROWS_PER_PAGE}: {len(docs)} docs (total: {total})")

            for doc in docs:
                if max_docs and fetched >= max_docs:
                    return
                yield doc
                fetched += 1

            start += ROWS_PER_PAGE
            if start >= total:
                break

            time.sleep(1.0)

        logger.info(f"Fetched {fetched}/{total} sanctions records")

    def fetch_updates(self, since: datetime) -> Iterator[Dict[str, Any]]:
        """Fetch sanctions modified since a given date."""
        since_str = since.strftime('%Y-%m-%dT00:00:00Z')
        params = {
            'q': f'sn_modificationDate:[{since_str} TO NOW] OR sn_date:[{since_str} TO NOW]',
            'rows': ROWS_PER_PAGE,
            'start': 0,
            'wt': 'json',
            'sort': 'sn_date desc',
            'fl': '*',
        }
        try:
            resp = self.session.get(SOLR_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for doc in data['response']['docs']:
                yield doc
        except requests.exceptions.RequestException as e:
            logger.error(f"Update query failed: {e}")

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a Solr sanctions document to standard schema."""
        sanction_id = str(raw.get('sn_sanctionEsmaID', raw.get('id', '')))
        entity_name = self._clean_entity_name(raw.get('sn_entityName', ''))
        country = raw.get('sn_countryName', '')
        framework = raw.get('sn_sanctionLegalFrameworkName', '')
        nature = raw.get('sn_natureFullName', '')
        nca = raw.get('sn_ncaCodeFullName', '')
        text = self._clean_entity_name(raw.get('sn_text', ''))  # strip HTML tags

        # Parse date
        date_raw = raw.get('sn_date', '')
        parsed_date = None
        if date_raw:
            try:
                dt = datetime.fromisoformat(date_raw.replace('Z', '+00:00'))
                parsed_date = dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                pass

        # Build title
        title_parts = [f"Sanction against {entity_name}" if entity_name else "Sanction"]
        if framework:
            title_parts.append(f"({framework})")
        if country:
            title_parts.append(f"— {country}")
        title = " ".join(title_parts)

        url = f"https://registers.esma.europa.eu/publication/details?core=esma_registers_sanctions&docId=sn{sanction_id}"

        return {
            '_id': f"ESMA-SN-{sanction_id}",
            '_source': SOURCE_ID,
            '_type': 'case_law',
            '_fetched_at': datetime.utcnow().isoformat(),
            'sanction_id': sanction_id,
            'entity_name': entity_name,
            'title': title,
            'text': text,
            'date': parsed_date,
            'url': url,
            'legal_framework': framework,
            'nature': nature,
            'country': country,
            'nca': nca,
            'lei': raw.get('sn_entityLEI', ''),
            'language': raw.get('sn_lan_orig', ''),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description='ESMA Sanctions Register fetcher')
    parser.add_argument('command', choices=['bootstrap', 'bootstrap-fast'],
                        help='Command to run')
    parser.add_argument('--sample', action='store_true',
                        help='Fetch only sample records (15)')
    parser.add_argument('--full', action='store_true',
                        help='Fetch all records')
    args = parser.parse_args()

    fetcher = ESMASanctionsFetcher()
    sample_dir = Path(__file__).parent / 'sample'
    sample_dir.mkdir(exist_ok=True)

    if args.sample:
        max_docs = 15
        logger.info("Fetching sample (15 records)...")
    elif args.full:
        max_docs = None
        logger.info("Fetching ALL sanctions records...")
    else:
        max_docs = 15
        logger.info("Fetching sample (15 records, use --full for all)...")

    count = 0
    skipped = 0

    for raw in fetcher.fetch_all(max_docs=max_docs):
        normalized = fetcher.normalize(raw)

        if not normalized.get('text', '').strip():
            skipped += 1
            continue

        filename = f"{normalized['_id'].replace('/', '_')}.json"
        filepath = sample_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)

        count += 1
        logger.info(f"[{count}] {normalized['title'][:70]}... ({len(normalized['text']):,} chars)")

    logger.info(f"Done. Saved {count} records, skipped {skipped} (no text).")

    if count > 0:
        files = list(sample_dir.glob('*.json'))
        total_chars = sum(
            len(json.load(open(f)).get('text', '')) for f in files
        )
        avg = total_chars // len(files) if files else 0
        logger.info(f"Average text: {avg:,} chars/doc across {len(files)} files")


if __name__ == '__main__':
    main()
