#!/usr/bin/env python3
"""
Hungarian National Authority for Trade and Consumer Protection (NFKH) Data Fetcher

Fetches consumer protection decisions from NFKH via their Strapi CMS API.
Each decision includes metadata and a PDF file; text extracted via pdfminer.

Data source: https://nkfh.gov.hu/hatarozatok
License: Public (Government of Hungary)
"""

import io
import json
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import requests
from pdfminer.high_level import extract_text as pdf_extract_text

# Public API token embedded in the Nuxt frontend
API_TOKEN = (
    "c6b5b231906490dedaa3f69dfbee835b19283db4c39cce2e783da24cb7e7d9d4"
    "7b52f46ff679bb328aaa4e974f034488521939e2ce0f7548450afeddad3043dd1"
    "0fe05eb2e9badbf893a41f951ad2fea00cf076cafc714cca19c1731ff00feb1f9"
    "1eb1761de807cda5b7195786e0a0cf1e6f83331370b40bda6765f6fe6ddbd4"
)
API_URL = "https://api.nkfh.gov.hu/api/decisions"
CDN_URL = "https://cdn.nkfh.gov.hu"
PAGE_SIZE = 25
RATE_LIMIT_DELAY = 1.0


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json",
        "User-Agent": "LegalDataHunter/1.0 (legal research; open data collection)",
    })
    session.verify = True
    return session


def make_cdn_session() -> requests.Session:
    """Separate session for CDN downloads (no Bearer token — Azure rejects it)."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal research; open data collection)",
    })
    return session


_cdn_session: Optional[requests.Session] = None


def extract_pdf_text(session: requests.Session, pdf_url: str) -> Optional[str]:
    """Download a PDF and extract its text content."""
    global _cdn_session
    if _cdn_session is None:
        _cdn_session = make_cdn_session()
    try:
        resp = _cdn_session.get(pdf_url, timeout=60)
        resp.raise_for_status()
        pdf_bytes = resp.content
        if len(pdf_bytes) < 100 or not pdf_bytes[:5].startswith(b"%PDF"):
            return None
        text = pdf_extract_text(io.BytesIO(pdf_bytes))
        text = text.strip()
        return text if len(text) > 50 else None
    except Exception as e:
        print(f"  PDF extraction error: {e}", file=sys.stderr)
        return None


def normalize(record: dict, text: str, pdf_url: str) -> dict:
    """Transform a Strapi record into the standard schema."""
    case_id = record.get("caseId", "")
    doc_id = hashlib.sha256(case_id.encode()).hexdigest()[:16]

    return {
        "_id": doc_id,
        "_source": "HU/NFKH",
        "_type": "doctrine",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"{case_id} — {record.get('authority', 'NFKH')}",
        "text": text,
        "date": record.get("effectiveDate"),
        "url": pdf_url,
        "case_id": case_id,
        "authority": record.get("authority", ""),
        "legal_basis": record.get("legalBasis", ""),
        "participant_name": record.get("participantName", ""),
        "participant_address": record.get("participantAddress", ""),
        "appealed": record.get("appealed"),
    }


def fetch_all(
    session: requests.Session, max_pages: Optional[int] = None
) -> Generator[dict, None, None]:
    """Yield all normalized documents from the Strapi API."""
    page = 1
    total_pages = None
    doc_count = 0

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": PAGE_SIZE,
            "populate": "*",
            "sort": "effectiveDate:desc",
        }
        try:
            resp = session.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"API error on page {page}: {e}", file=sys.stderr)
            break

        records = data.get("data", [])
        meta = data.get("meta", {}).get("pagination", {})
        total_pages = meta.get("pageCount", 1)
        total_records = meta.get("total", 0)

        if page == 1:
            print(
                f"API: {total_records} decisions across {total_pages} pages",
                file=sys.stderr,
            )

        if not records:
            break

        for record in records:
            pdf_file = record.get("decisionFile")
            if not pdf_file or not pdf_file.get("url"):
                continue

            pdf_url = pdf_file["url"]
            case_id = record.get("caseId", "unknown")

            time.sleep(RATE_LIMIT_DELAY)
            print(f"  Fetching PDF: {case_id}", file=sys.stderr)
            text = extract_pdf_text(session, pdf_url)
            if not text:
                print(f"  Skipped (no text extracted): {case_id}", file=sys.stderr)
                continue

            doc_count += 1
            yield normalize(record, text, pdf_url)

        print(f"Page {page}/{total_pages} done ({doc_count} docs so far)", file=sys.stderr)

        page += 1
        effective_max = max_pages if max_pages else total_pages
        if page > effective_max:
            break

        time.sleep(RATE_LIMIT_DELAY)

    print(f"Total documents fetched: {doc_count}", file=sys.stderr)


def bootstrap_sample(num_pages: int = 2):
    """Fetch a sample of documents and save to sample/."""
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    session = make_session()
    count = 0

    for record in fetch_all(session, max_pages=num_pages):
        count += 1
        out_path = sample_dir / f"{record['_id']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"  Saved sample {count}: {record['title'][:60]}", file=sys.stderr)
        if count >= 15:
            break

    print(
        f"\nSample complete: {count} documents saved to {sample_dir}",
        file=sys.stderr,
    )
    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NFKH data fetcher")
    parser.add_argument(
        "command", choices=["bootstrap", "bootstrap-fast"], help="Command to run"
    )
    parser.add_argument("--sample", action="store_true", help="Fetch sample data only")
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Maximum number of API pages to process",
    )
    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample:
            bootstrap_sample()
        else:
            # Full run: stream every record to data/records.jsonl so the ingest
            # pipeline finds the whole corpus (previously printed to stdout only).
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"
            session = make_session()
            count = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in fetch_all(session, max_pages=args.max_pages):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
            print(f"Total: {count} records written -> {jsonl_path}", file=sys.stderr)
