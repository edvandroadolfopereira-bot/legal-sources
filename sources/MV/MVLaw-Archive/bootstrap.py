#!/usr/bin/env python3
"""
MV/MVLaw-Archive -- Maldives Attorney General old MVLaw English translations

17 English translations of key Maldivian laws from old.mvlaw.gov.mv.
PDFs downloaded and text extracted via pdfplumber.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.MV.MVLaw-Archive")

SOURCE_ID = "MV/MVLaw-Archive"
BASE_URL = "https://old.mvlaw.gov.mv"

DOCUMENTS = [
    {"id": "FIL", "title": "Law of Foreign Investments in the Republic of Maldives", "file": "FIL.pdf"},
    {"id": "PC1", "title": "Penal Code Chapter 1", "file": "PC1.pdf"},
    {"id": "PC2", "title": "Penal Code Chapter 2", "file": "PC2.pdf"},
    {"id": "Environment", "title": "Environmental Protection and Preservations Act of Maldives", "file": "Environment.pdf"},
    {"id": "Consumer", "title": "Consumer Protection Act", "file": "Consumer.pdf"},
    {"id": "Terrorism", "title": "Prevention of Terrorism Act", "file": "Terrorism.pdf"},
    {"id": "PC3", "title": "Penal Code Chapter 3", "file": "PC3.pdf"},
    {"id": "Partnership", "title": "Partnership Act of Maldives", "file": "Partnership.pdf"},
    {"id": "PC4", "title": "Penal Code Chapter 4", "file": "PC4.pdf"},
    {"id": "Company", "title": "The Company Act of the Maldives", "file": "Company.pdf"},
    {"id": "Corruption", "title": "Prevention and Prohibition of Corruption Act", "file": "Corruption.pdf"},
    {"id": "Family", "title": "Family Act", "file": "Family.pdf"},
    {"id": "Land", "title": "Maldivian Land Act", "file": "Land.pdf"},
    {"id": "AssocAct", "title": "Association Act", "file": "AssocAct.pdf"},
    {"id": "CabinetMinisters", "title": "Addressing of Questions to Cabinet Minister's Act", "file": "CabinetMinisters.pdf"},
    {"id": "HRC", "title": "Human Rights Commission Act", "file": "HRC.pdf"},
    {"id": "Securities", "title": "Securities Act", "file": "Securities.pdf"},
    {"id": "Constitution2008EN", "title": "Constitution of the Republic of Maldives 2008 (English)", "file": "../ganoon/QaanoonAsaasee/English-constitution.pdf"},
]


def curl_download(url: str, dest: str, max_attempts: int = 3) -> bool:
    """Download a file via curl."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '60',
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-o', dest, url],
                capture_output=True, text=True, timeout=70
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
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(parts)
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", pdf_path, e)
        return ""


def normalize(doc: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    """Normalize a document record."""
    if not text or len(text) < 50:
        return None
    if doc['file'].startswith("../"):
        pdf_url = f"{BASE_URL}/pdf/{doc['file'][3:]}"
    else:
        pdf_url = f"{BASE_URL}/pdf/translation/{doc['file']}"
    return {
        "_id": f"mv-mvlaw-{doc['id'].lower()}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": doc["title"],
        "text": text,
        "date": None,
        "url": pdf_url,
        "language": "en",
    }


def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all documents with full text from PDFs."""
    docs = DOCUMENTS[:18] if sample else DOCUMENTS
    count = 0

    for doc in docs:
        if doc['file'].startswith("../"):
            pdf_url = f"{BASE_URL}/pdf/{doc['file'][3:]}"
        else:
            pdf_url = f"{BASE_URL}/pdf/translation/{doc['file']}"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            logger.info("Downloading: %s", doc["title"])
            if not curl_download(pdf_url, tmp_path):
                logger.warning("Failed to download: %s", pdf_url)
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
            pdf_url = f"{BASE_URL}/pdf/translation/Consumer.pdf"
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            ok = curl_download(pdf_url, tmp_path)
            if ok:
                text = extract_pdf_text(tmp_path)
                logger.info("Test OK: %d chars from Consumer.pdf", len(text))
            os.unlink(tmp_path)
            sys.exit(0 if ok and text else 1)
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
