#!/usr/bin/env python3
"""
HT/MEF-Budget -- Haiti Ministry of Economy & Finance — Lois de Finances

Budget laws, decrees, and finance documents from mef.gouv.ht/budgets/lois.
~112 PDF documents spanning 1849-2026. PDFs downloaded and text extracted
via pdfplumber.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.HT.MEF-Budget")

SOURCE_ID = "HT/MEF-Budget"
PAGE_URL = "https://mef.gouv.ht/budgets/lois"

FRENCH_MONTHS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
    "fevrier": "02", "aout": "08",
    "janv": "01", "févr": "02", "avr": "04", "juil": "07",
    "sept": "09", "oct": "10", "nov": "11", "déc": "12",
}


def parse_french_date(text: str) -> Optional[str]:
    """Extract date from French text like 'du 22 septembre 2025'."""
    text_lower = text.lower()
    m = re.search(
        r'(?:du\s+)?(\d{1,2})\s*(?:er\s+)?'
        r'(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|'
        r'septembre|octobre|novembre|décembre|'
        r'janv|févr|avr|juil|sept|oct|nov|déc)\.?\s+(\d{4})',
        text_lower
    )
    if m:
        day = int(m.group(1))
        month = FRENCH_MONTHS.get(m.group(2), "01")
        year = m.group(3)
        return f"{year}-{month}-{day:02d}"

    # Try to extract fiscal year like "2024-2025" or "Exercice 2024-2025"
    m = re.search(r'(?:exercice\s+(?:fiscal\s+)?)?(\d{4})[–-](\d{4})', text_lower)
    if m:
        return f"{m.group(1)}-10-01"  # Haitian fiscal year starts Oct 1

    # Try just a year
    m = re.search(r'\b(1[89]\d{2}|20[012]\d)\b', text)
    if m:
        return f"{m.group(1)}-01-01"

    return None


def scrape_document_list() -> List[Dict[str, str]]:
    """Scrape the budget page and return list of {title, pdf_url, date}."""
    result = subprocess.run(
        ['curl', '-s', '-L', '--max-time', '30',
         '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
         PAGE_URL],
        capture_output=True, text=True, timeout=40
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch page: {result.stderr}")

    html = result.stdout

    # Extract h4/h5/h6 title + next PDF link pairs
    blocks = re.findall(
        r'<h[4-6][^>]*>(.*?)</h[4-6]>.*?'
        r'<a[^>]*href="(https://mef\.gouv\.ht/storage/[^"]*\.pdf)"',
        html, re.DOTALL
    )

    docs = []
    seen_urls = set()
    for title_html, pdf_url in blocks:
        title = unescape(re.sub(r'<[^>]+>', '', title_html).strip())
        title = re.sub(r'\s+', ' ', title)

        if not title or pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        # Skip non-legal items (payroll data, reports, citizen budgets)
        title_lower = title.lower()
        skip_keywords = ["effectif et masse salariale", "ministere  de l'economie"]
        if any(kw in title_lower for kw in skip_keywords):
            continue

        date = parse_french_date(title)

        doc_id = hashlib.md5(pdf_url.encode()).hexdigest()[:12]
        docs.append({
            "id": f"ht-mef-budget-{doc_id}",
            "title": title,
            "date": date,
            "pdf_url": pdf_url,
        })

    logger.info("Found %d budget documents on page", len(docs))
    return docs


def curl_download(url: str, dest: str, max_attempts: int = 3) -> bool:
    """Download a file via curl."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '90',
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-o', dest, url],
                capture_output=True, text=True, timeout=100
            )
            if result.returncode == 0 and os.path.getsize(dest) > 500:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
        delay = min(5 * (2 ** attempt), 30)
        logger.warning("Download attempt %d failed for %s", attempt + 1, url)
        time.sleep(delay)
    return False


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text = re.sub(r'\(cid:\d+\)', ' ', text)
                    text = re.sub(r' {2,}', ' ', text)
                    parts.append(text.strip())
            return "\n\n".join(parts)
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", pdf_path, e)
        return ""


def normalize(doc: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    """Normalize a document record."""
    if not text or len(text) < 50:
        return None
    return {
        "_id": doc["id"],
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": doc["title"],
        "text": text,
        "date": doc["date"],
        "url": doc["pdf_url"],
        "language": "fr",
    }


def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all documents with full text from PDFs."""
    docs = scrape_document_list()
    if sample:
        docs = docs[:20]  # fetch a few extra in case some fail

    count = 0
    for doc in docs:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            logger.info("Downloading: %s", doc["title"][:70])
            if not curl_download(doc["pdf_url"], tmp_path):
                logger.warning("Failed to download: %s", doc["pdf_url"])
                continue

            text = extract_pdf_text(tmp_path)
            if not text or len(text) < 50:
                logger.warning("No text extracted for: %s", doc["title"])
                continue

            record = normalize(doc, text)
            if record:
                count += 1
                logger.info("[%d] %s (%d chars)", count, doc["title"][:60], len(text))
                yield record

                if sample and count >= 15:
                    break
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        time.sleep(2.0)

    logger.info("Total records: %d", count)


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample] [--full]")
        sys.exit(1)

    command = args[0]
    sample_mode = "--sample" in args

    if command == "test":
        try:
            docs = scrape_document_list()
            if docs:
                logger.info("Test OK: found %d documents", len(docs))
                sys.exit(0)
            else:
                logger.error("Test failed: no documents found")
                sys.exit(1)
        except Exception as e:
            logger.error("Test failed: %s", e)
            sys.exit(1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for record in fetch_all(sample=sample_mode):
            if sample_mode:
                fname = re.sub(r'[^\w\-]', '_', record["_id"])[:80] + ".json"
                out_file = sample_dir / fname
                out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                count += 1
                logger.info("Sample %d saved: %s", count, fname)
            else:
                print(json.dumps(record, ensure_ascii=False))
                count += 1

        logger.info("Done: %d records %s", count, "(sample)" if sample_mode else "(full)")
        if count == 0:
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
