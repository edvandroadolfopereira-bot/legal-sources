#!/usr/bin/env python3
"""
EDPB Article 60 One-Stop-Shop Register — Data Fetcher

Fetches final decisions by EU national data protection authorities (DPAs)
under the GDPR cooperation mechanism (Article 60). The register contains
~2,400 decisions with metadata and PDF summaries.

Source: https://www.edpb.europa.eu/our-work-tools/consistency-findings/register-for-article-60-final-decisions_en
Access: HTML scraping of listing pages + PDF download for full text
Auth: None required
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# PDF extraction
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from common.pdf_extract import extract_pdf_markdown
    HAS_COMMON_PDF = True
except ImportError:
    HAS_COMMON_PDF = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_ID = "EU/EDPB-OSSRegister"
BASE_URL = "https://www.edpb.europa.eu"
REGISTER_PATH = "/our-work-tools/consistency-findings/register-for-article-60-final-decisions_en"


class EDPBOSSRegisterFetcher:
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

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes."""
        if HAS_COMMON_PDF:
            return extract_pdf_markdown(
                source=SOURCE_ID, source_id="", pdf_bytes=pdf_bytes, table="case_law"
            ) or ""

        if HAS_PDFPLUMBER:
            import io
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages]
                    return "\n\n".join(pages).strip()
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")
                return ""

        return ""

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format."""
        for fmt in ['%d %B %Y', '%d %b %Y', '%B %d, %Y', '%d/%m/%Y', '%Y-%m-%d']:
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None

    def _parse_listing_page(self, html: str) -> List[Dict[str, Any]]:
        """Parse a register listing page and extract decision metadata."""
        soup = BeautifulSoup(html, 'html.parser')
        decisions = []

        nodes = soup.find_all('div', class_='node--type-edpb-article-60-final-decision')

        for node in nodes:
            try:
                case_id_el = node.find(class_='field--name-field-edpb-art-60-id')
                case_id = case_id_el.get_text(strip=True) if case_id_el else None
                if not case_id:
                    continue

                date_el = node.find(class_='news-date')
                date_str = date_el.get_text(strip=True) if date_el else ''

                lsa_el = node.find(class_='field--name-field-edpb-lsa')
                lsa = lsa_el.find(class_='field__item').get_text(strip=True) if lsa_el and lsa_el.find(class_='field__item') else ''

                csa_el = node.find(class_='field--name-field-edpb-csa')
                csa = [i.get_text(strip=True) for i in csa_el.find_all(class_='field__item')] if csa_el else []

                ref_el = node.find(class_='field--name-field-edpb-main-legal-reference')
                legal_refs = [i.get_text(strip=True) for i in ref_el.find_all(class_='field__item')] if ref_el else []

                kw_el = node.find(class_='field--name-field-edpb-art-60-keywords')
                keywords = [i.get_text(strip=True) for i in kw_el.find_all(class_='field__item')] if kw_el else []

                out_el = node.find(class_='field--name-field-edpb-types-of-decision')
                outcomes = [i.get_text(strip=True) for i in out_el.find_all(class_='field__item')] if out_el else []

                pdf_link = node.find('a', href=lambda h: h and '.pdf' in h.lower())
                pdf_url = urljoin(BASE_URL, pdf_link['href']) if pdf_link else None

                decisions.append({
                    'case_id': case_id,
                    'date_str': date_str,
                    'lsa': lsa,
                    'csa': csa,
                    'legal_references': legal_refs,
                    'keywords': keywords,
                    'outcomes': outcomes,
                    'pdf_url': pdf_url,
                })

            except Exception as e:
                logger.warning(f"Failed to parse decision node: {e}")

        return decisions

    def fetch_all(self, max_docs: int = None) -> Iterator[Dict[str, Any]]:
        """Fetch decisions from the register with full text from PDFs."""
        page = 0
        fetched = 0
        consecutive_empty = 0

        while True:
            if max_docs and fetched >= max_docs:
                return

            url = f"{BASE_URL}{REGISTER_PATH}?page={page}"
            logger.info(f"Fetching page {page}...")

            resp = self._request(url)
            if not resp:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                page += 1
                continue

            decisions = self._parse_listing_page(resp.text)
            if not decisions:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    logger.info(f"No more decisions (page {page})")
                    break
                page += 1
                continue

            consecutive_empty = 0

            for dec in decisions:
                if max_docs and fetched >= max_docs:
                    return

                text = ""
                if dec['pdf_url']:
                    pdf_resp = self._request(dec['pdf_url'], timeout=120)
                    if pdf_resp and len(pdf_resp.content) > 0:
                        text = self._extract_pdf_text(pdf_resp.content)
                    time.sleep(1.0)

                dec['text'] = text
                yield dec
                fetched += 1

            page += 1
            time.sleep(2.0)

        logger.info(f"Total fetched: {fetched}")

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize to standard schema."""
        case_id = raw['case_id']
        lsa = raw.get('lsa', '')
        date = self._parse_date(raw.get('date_str', ''))

        title_parts = [f"GDPR Art. 60 Decision {case_id}"]
        if lsa:
            title_parts.append(f"(LSA: {lsa})")
        legal_refs = raw.get('legal_references', [])
        if legal_refs:
            title_parts.append(f"— {'; '.join(legal_refs[:2])}")
        title = " ".join(title_parts)

        url = f"{BASE_URL}{REGISTER_PATH}"

        return {
            '_id': case_id,
            '_source': SOURCE_ID,
            '_type': 'case_law',
            '_fetched_at': datetime.utcnow().isoformat(),
            'case_id': case_id,
            'title': title,
            'text': raw.get('text', ''),
            'date': date,
            'url': url,
            'lsa': lsa,
            'csa': raw.get('csa', []),
            'legal_references': raw.get('legal_references', []),
            'keywords': raw.get('keywords', []),
            'outcome': raw.get('outcomes', []),
            'pdf_url': raw.get('pdf_url', ''),
        }


def main():
    parser = argparse.ArgumentParser(description='EDPB Art. 60 OSS Register fetcher')
    parser.add_argument('command', choices=['bootstrap', 'bootstrap-fast'])
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()

    if not HAS_PDFPLUMBER and not HAS_COMMON_PDF:
        logger.error("No PDF extraction available. Install pdfplumber: pip install pdfplumber")
        sys.exit(1)

    fetcher = EDPBOSSRegisterFetcher()
    sample_dir = Path(__file__).parent / 'sample'
    sample_dir.mkdir(exist_ok=True)

    target = 15 if args.sample or not args.full else None
    # For sample mode, fetch more raw docs to compensate for scanned PDFs (0 text)
    max_docs = target * 4 if target else None
    logger.info(f"Fetching {'sample (target ' + str(target) + ')' if target else 'ALL'} decisions...")

    count = 0
    skipped = 0

    for raw in fetcher.fetch_all(max_docs=max_docs):
        normalized = fetcher.normalize(raw)

        if len(normalized.get('text', '')) < 50:
            skipped += 1
            logger.warning(f"Skipped {normalized['case_id']} — insufficient text ({len(normalized.get('text',''))} chars)")
            continue

        filename = normalized['_id'].replace(':', '_').replace('/', '_') + '.json'
        filepath = sample_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)

        count += 1
        logger.info(f"[{count}] {normalized['case_id']} — {len(normalized['text']):,} chars")

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
