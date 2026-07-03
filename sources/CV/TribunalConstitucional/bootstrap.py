#!/usr/bin/env python3
"""
CV/TribunalConstitucional - Cabo Verde Constitutional Court Decisions

Fetches decisions (acórdãos) and advisory opinions (pareceres) of the
Tribunal Constitucional de Cabo Verde. Decisions are published as direct
PDF downloads from the court's Joomla site, listed on the "últimas decisões"
page and per-year archive pages (2017-2026). Full text is extracted with pypdf.

Data source: https://www.tribunalconstitucional.cv/
License: Public domain (official judicial decisions of the Republic of Cabo Verde)
"""

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import unquote, urljoin

import pypdf
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://www.tribunalconstitucional.cv/"
SOURCE_ID = "CV/TribunalConstitucional"
SAMPLE_DIR = Path(__file__).parent / "sample"

# Listing pages that contain direct /download/.../*.pdf links.
# "ultimas-decisoes" first (newest), then per-year archives.
LISTING_PAGES = [
    "https://www.tribunalconstitucional.cv/index.php/ultimas-decisoes/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2025/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2024/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2023/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2022/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2021/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2020/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes2019/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2018/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-2017/",
    "https://www.tribunalconstitucional.cv/index.php/decisoes-sumarias/",
]

MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


class CaboVerdeTCFetcher:
    """Fetcher for Cabo Verde Constitutional Court decisions."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Legal-Data-Hunter/1.0',
        })
        self.session.verify = False  # site presents an expired/incomplete chain
        self._seen_urls = set()

    def get_pdf_links(self, listing_url: str) -> List[Dict[str, str]]:
        """Extract direct decision PDF links from a listing page."""
        try:
            resp = self.session.get(listing_url, timeout=45)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {listing_url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        entries = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/download/' not in href or not href.lower().endswith('.pdf'):
                continue
            href = urljoin(listing_url, href)
            if href in self._seen_urls:
                continue
            self._seen_urls.add(href)

            link_text = a.get_text(strip=True)
            # Filename (last path segment) is the most descriptive title.
            filename = unquote(href.split('/')[-1])
            filename_title = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
            filename_title = re.sub(r'^\d{1,3}\s*-\s*', '', filename_title).strip()
            title = filename_title if len(filename_title) > 8 else (link_text or filename_title)
            entries.append({"url": href, "title": title, "filename": filename})

        logger.info(f"Found {len(entries)} decision PDFs from {listing_url.rstrip('/').split('/')[-1]}")
        return entries

    def download_pdf_text(self, url: str) -> Optional[str]:
        """Download a decision PDF and extract clean full text."""
        try:
            resp = self.session.get(url, timeout=180)
            if resp.status_code != 200:
                return None
            if resp.content[:4] != b'%PDF':
                return None
            if len(resp.content) < 1500:
                return None
            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text)
            # Normalize whitespace produced by PDF layout extraction.
            full_text = re.sub(r'[ \t]+\n', '\n', full_text)
            full_text = re.sub(r'\n{3,}', '\n\n', full_text)
            full_text = full_text.strip()
            return full_text if len(full_text) > 200 else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {url}: {e}")
            return None

    def extract_metadata(self, entry: Dict[str, str], text: str) -> Dict[str, Any]:
        """Derive case number, document type, year and date."""
        title = entry["title"]

        # Year from /YYYY/ path segment (reliable), fallback to title.
        year = None
        m = re.search(r'/download/\d+/(\d{4})/', entry["url"])
        if m:
            year = int(m.group(1))
        if not year:
            m = re.search(r'\b(20\d{2})\b', title)
            if m:
                year = int(m.group(1))

        # Document type + number (Acórdão N/YYYY, Parecer N/YYYY, Decisão ...).
        doc_type = "acordao"
        case_number = None
        m = re.search(r'(Ac[oó]rd[aã]o|Parecer|Decis[aã]o)\s*n?\.?[ºo]?\s*(\d+)[-/](\d{4})',
                      title, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            if kind.startswith("parecer"):
                doc_type = "parecer"
            elif kind.startswith("decis"):
                doc_type = "decisao_sumaria"
            case_number = f"{m.group(2)}/{m.group(3)}"

        # Actual decision date from PDF body ("Praia, aos 30 de março de 2026").
        # Decisions are signed/dated at the END, so scan all matches and prefer
        # the LAST one whose year matches the reliable URL-path year — this avoids
        # picking up dates of cited/earlier decisions in the body.
        date = None
        candidates = []
        for dm in re.finditer(r'(\d{1,2})\s+de\s+([a-zçã]+)\s+de\s+(\d{4})', text, re.IGNORECASE):
            day = int(dm.group(1))
            month = MONTHS_PT.get(dm.group(2).lower())
            yr = int(dm.group(3))
            if month and 1 <= day <= 31:
                candidates.append((yr, month, day))
        if candidates:
            matching = [c for c in candidates if year and c[0] == year]
            chosen = matching[-1] if matching else candidates[-1]
            date = f"{chosen[0]:04d}-{chosen[1]:02d}-{chosen[2]:02d}"
            if not year:
                year = chosen[0]
        if not date and year:
            date = f"{year}-01-01"

        return {"year": year, "case_number": case_number, "doc_type": doc_type, "date": date}

    def normalize(self, entry: Dict[str, str], text: str) -> Dict[str, Any]:
        """Normalize into the standard schema."""
        doc_id = hashlib.sha256(entry["url"].encode()).hexdigest()[:16]
        meta = self.extract_metadata(entry, text)
        title = entry["title"].replace('  ', ' ').strip()
        return {
            "_id": f"CV-TC-{doc_id}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": meta["date"],
            "url": entry["url"],
            "case_number": meta["case_number"],
            "doc_type": meta["doc_type"],
            "year": meta["year"],
            "court": "Tribunal Constitucional de Cabo Verde",
            "country": "CV",
            "language": "pt",
        }

    def _iter_entries(self) -> Iterator[Dict[str, str]]:
        for listing_url in LISTING_PAGES:
            for entry in self.get_pdf_links(listing_url):
                yield entry
            time.sleep(1.0)

    def fetch_all(self) -> Iterator[Dict[str, Any]]:
        """Yield all decisions with full text."""
        for i, entry in enumerate(self._iter_entries()):
            logger.info(f"  [{i+1}] {entry['title'][:60]}")
            time.sleep(1.5)
            text = self.download_pdf_text(entry["url"])
            if text:
                yield self.normalize(entry, text)
            else:
                logger.warning(f"    No text extracted: {entry['url']}")

    def fetch_sample(self, max_records: int = 15) -> Iterator[Dict[str, Any]]:
        """Yield a sample of recent decisions with full text."""
        count = 0
        for entry in self._iter_entries():
            if count >= max_records:
                return
            time.sleep(1.5)
            text = self.download_pdf_text(entry["url"])
            if not text:
                continue
            record = self.normalize(entry, text)
            count += 1
            logger.info(f"  Sample {count}/{max_records}: {record['title'][:55]} ({len(text)} chars)")
            yield record

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield decisions with date on/after `since` (ISO date)."""
        for record in self.fetch_all():
            if not since or (record.get("date") and record["date"] >= since):
                yield record


def _run(records_iter) -> int:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in records_iter:
        safe_id = record["_id"].replace("/", "_")
        with open(SAMPLE_DIR / f"{safe_id}.json", "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        count += 1
    logger.info(f"Bootstrap complete: {count} records saved to {SAMPLE_DIR}")
    return count


def main():
    parser = argparse.ArgumentParser(description="CV/TribunalConstitucional Fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    parser.add_argument("--full", action="store_true", help="Full bootstrap")
    args = parser.parse_args()

    fetcher = CaboVerdeTCFetcher()
    if args.sample or not args.full:
        _run(fetcher.fetch_sample(max_records=15))
    else:
        _run(fetcher.fetch_all())


if __name__ == "__main__":
    main()
