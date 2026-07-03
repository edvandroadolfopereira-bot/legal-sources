#!/usr/bin/env python3
"""
PT/SRIJ -- Portuguese Gaming Regulation Authority Fetcher

Fetches legislation, instructions, and regulatory guidance from the SRIJ
(Serviço de Regulação e Inspeção de Jogos), part of Turismo de Portugal.

Strategy:
  - Discovery: Scrape the legislation page at
    srij.turismodeportugal.pt/pt/legislacao for PDF links and titles
  - Full text: Download PDFs and extract text via pdfplumber
  - Documents include: decree-laws, instructions, orientations, guidelines

License: Public (Portuguese government regulatory documents)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch sample records for validation
"""

import html as html_mod
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote, urljoin

import pdfplumber
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.srij.turismodeportugal.pt"
LEGISLATION_URL = f"{BASE_URL}/pt/legislacao"
SOURCE_ID = "PT/SRIJ"
SOURCE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = SOURCE_DIR / "sample"


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
    return "\n\n".join(text_parts)


def clean_text(text: str) -> str:
    """Clean extracted text."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def guess_date_from_title(title: str) -> Optional[str]:
    """Try to extract a date from the document title."""
    months = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
        "abril": "04", "maio": "05", "junho": "06", "julho": "07",
        "agosto": "08", "setembro": "09", "outubro": "10",
        "novembro": "11", "dezembro": "12",
    }
    # Try "de DD de month de YYYY"
    m = re.search(r"de\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", title, re.I)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = m.group(3)
        if month_name in months:
            return f"{year}-{months[month_name]}-{day:02d}"

    # Try "de DD de month" without year — extract year from doc number
    m = re.search(r"de\s+(\d{1,2})\s+de\s+(\w+)\s*$", title, re.I)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        if month_name in months:
            # Try to find year from pattern like n.º NN/YYYY or /YYYY/
            ym = re.search(r"/(\d{4})[/\s,]", title)
            if ym:
                return f"{ym.group(1)}-{months[month_name]}-{day:02d}"

    # Try "DD/MM/YYYY"
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", title)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # Extract year from decree-law number: n.º XX/YYYY or n.º XX/YY
    m = re.search(r"n\.º\s+[\d-]+[A-Z]*/(\d{4})\b", title)
    if m:
        return f"{m.group(1)}-01-01"
    m = re.search(r"n\.º\s+[\d-]+[A-Z]*/(\d{2})\b", title)
    if m:
        yr = int(m.group(1))
        year = 1900 + yr if yr > 50 else 2000 + yr
        return f"{year}-01-01"

    return None


def guess_doc_type(title: str, url: str) -> str:
    """Classify document type from title."""
    title_lower = title.lower()
    if "decreto-lei" in title_lower or "decreto_lei" in title_lower:
        return "decreto-lei"
    if "decreto legislativo" in title_lower:
        return "decreto-legislativo-regional"
    if "decreto regulamentar" in title_lower:
        return "decreto-regulamentar"
    if "portaria" in title_lower:
        return "portaria"
    if "regulamento" in title_lower:
        return "regulamento"
    if "instrução" in title_lower or "instruc" in title_lower:
        return "instrução"
    if "orientação" in title_lower or "orientac" in title_lower:
        return "orientação"
    if "linhas de orientação" in title_lower or "linhas_orientacao" in title_lower:
        return "orientação"
    if "informação vinculativa" in title_lower or "informacao_vinculativa" in title_lower:
        return "informação-vinculativa"
    if "lei" in title_lower:
        return "lei"
    return "regulamento"


def make_id(url: str) -> str:
    """Generate a stable ID from the PDF URL."""
    filename = unquote(url.split("/")[-1])
    filename = re.sub(r"\.pdf$", "", filename, flags=re.I)
    filename = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
    filename = re.sub(r"_+", "_", filename).strip("_")
    return filename[:120]


class SRIJFetcher:
    """Fetcher for Portuguese Gaming Regulation Authority legislation."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.session.verify = False  # SRIJ has SSL cert issues

    def _discover_documents(self) -> List[Dict[str, str]]:
        """Scrape the legislation page for PDF links and their titles."""
        import warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

        logger.info(f"Fetching legislation page: {LEGISLATION_URL}")
        resp = self.session.get(LEGISLATION_URL, timeout=30)
        resp.raise_for_status()
        html = resp.text

        documents = []
        seen_urls = set()

        # SRIJ uses Drupal with this structure per document:
        #   <div class="item-legislation">
        #     <div class="item-legislation-title"><span>TITLE</span></div>
        #     <div class="item-legislation-lead"><span>DESCRIPTION</span></div>
        #     <div class="item-legislation-document"><a href="URL.pdf">Consultar</a></div>
        #   </div>
        item_pattern = re.compile(
            r'<div\s+class="item-legislation">\s*'
            r'<div\s+class="item-legislation-title"><span>(.*?)</span></div>\s*'
            r'<div\s+class="item-legislation-lead"><span>(.*?)</span></div>\s*'
            r'<div\s+class="item-legislation-document"><a\s+href="([^"]*\.pdf)"',
            re.S | re.I,
        )

        for match in item_pattern.finditer(html):
            title = html_mod.unescape(re.sub(r"<[^>]+>", "", match.group(1)).strip())
            description = html_mod.unescape(re.sub(r"<[^>]+>", "", match.group(2)).strip())
            url = match.group(3)

            # Force HTTPS (HTTP times out on this server)
            url = url.replace("http://", "https://")

            if url.startswith("/"):
                url = BASE_URL + url
            elif not url.startswith("http"):
                url = urljoin(LEGISLATION_URL, url)

            if "/css/" in url or "/js/" in url:
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            documents.append({
                "url": url,
                "title": title,
                "description": description,
            })

        logger.info(f"Found {len(documents)} PDF documents")
        return documents

    def _download_pdf(self, url: str, retries: int = 3) -> Optional[bytes]:
        """Download a PDF file with retries."""
        import warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                if len(resp.content) < 100:
                    logger.warning(f"PDF too small ({len(resp.content)} bytes): {url}")
                    return None
                return resp.content
            except Exception as e:
                if attempt < retries - 1:
                    logger.info(f"Retry {attempt+1}/{retries} for {url.split('/')[-1]}")
                    time.sleep(3)
                else:
                    logger.warning(f"Failed to download {url}: {e}")
        return None

    def fetch_all(self, sample: bool = False) -> Iterator[Dict[str, Any]]:
        """Fetch all legislation documents."""
        documents = self._discover_documents()

        if sample:
            documents = documents[:15]

        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Downloading: {doc['title'][:80]}")

            pdf_bytes = self._download_pdf(doc["url"])
            if not pdf_bytes:
                continue

            text = extract_pdf_text(pdf_bytes)
            text = clean_text(text)

            if len(text) < 50:
                logger.warning(f"Insufficient text ({len(text)} chars): {doc['title']}")
                continue

            doc_id = make_id(doc["url"])
            date = guess_date_from_title(doc["title"])
            doc_type = guess_doc_type(doc["title"], doc["url"])

            record = {
                "_id": doc_id,
                "_source": SOURCE_ID,
                "_type": "legislation",
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": doc["title"],
                "text": text,
                "date": date,
                "url": doc["url"],
                "doc_type": doc_type,
                "language": "pt",
            }

            yield record
            time.sleep(1)


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw record (already normalized during fetch)."""
    return raw


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PT/SRIJ Bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch only sample records")
    parser.add_argument("--full", action="store_true",
                        help="Fetch all records")
    args = parser.parse_args()

    fetcher = SRIJFetcher()
    sample_mode = args.sample or (not args.full)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    for record in fetcher.fetch_all(sample=sample_mode):
        records.append(record)
        sample_path = SAMPLE_DIR / f"{record['_id'][:80]}.json"
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved: {sample_path.name} ({len(record['text'])} chars)")

    logger.info(f"Total records: {len(records)}")

    if records:
        text_lengths = [len(r["text"]) for r in records]
        logger.info(f"Text lengths: min={min(text_lengths)}, max={max(text_lengths)}, "
                     f"avg={sum(text_lengths)//len(text_lengths)}")

    # Write JSONL for pipeline
    jsonl_path = SOURCE_DIR / "data" / "records.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logger.info(f"Wrote {len(records)} records to {jsonl_path}")


if __name__ == "__main__":
    main()
