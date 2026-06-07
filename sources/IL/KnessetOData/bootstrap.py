#!/usr/bin/env python3
"""
Israel Knesset OData API — Legislation Fetcher

Fetches Israeli laws from the Knesset OData API (KNS_IsraelLaw),
downloads official gazette PDFs via KNS_DocumentLaw links on
fs.knesset.gov.il, and extracts full Hebrew text using pdfminer.

Data source: https://knesset.gov.il/Odata/ParliamentInfo.svc
License: Open Government Data (Israel)
"""

import io
import json
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import quote

import requests
from pdfminer.high_level import extract_text as pdf_extract_text

ODATA_BASE = "https://knesset.gov.il/Odata/ParliamentInfo.svc"
LAWS_ENDPOINT = f"{ODATA_BASE}/KNS_IsraelLaw"
DOCS_ENDPOINT = f"{ODATA_BASE}/KNS_DocumentLaw"
PAGE_SIZE = 50
RATE_LIMIT_DELAY = 1.5

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (legal research; open data collection)",
    "Accept": "application/json",
}


def odata_get(url: str, params: Optional[dict] = None) -> dict:
    """Make an OData request and return JSON response."""
    if params is None:
        params = {}
    params["$format"] = "json"
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_laws(skip: int = 0, top: int = PAGE_SIZE) -> list[dict]:
    """Fetch a page of laws from KNS_IsraelLaw."""
    data = odata_get(LAWS_ENDPOINT, {
        "$top": str(top),
        "$skip": str(skip),
        "$orderby": "IsraelLawID",
    })
    return data.get("value", [])


def fetch_docs_for_law(law_id: int) -> list[dict]:
    """Fetch document records for a specific law."""
    data = odata_get(DOCS_ENDPOINT, {
        "$filter": f"LawID eq {law_id}",
        "$orderby": "DocumentLawID desc",
    })
    return data.get("value", [])


def download_pdf_text(pdf_url: str) -> Optional[str]:
    """Download a PDF and extract its text content."""
    try:
        resp = requests.get(pdf_url, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        content = resp.content
        if len(content) < 100 or not content[:5].startswith(b"%PDF"):
            return None
        text = pdf_extract_text(io.BytesIO(content))
        text = text.strip()
        return text if len(text) > 50 else None
    except Exception as e:
        print(f"  PDF extraction error: {e}", file=sys.stderr)
        return None


def normalize(law: dict, text: str, pdf_url: str) -> dict:
    """Transform a raw law record into the standard schema."""
    law_id = law["IsraelLawID"]
    pub_date = law.get("PublicationDate")
    if pub_date:
        pub_date = pub_date.split("T")[0]

    return {
        "_id": f"il-knesset-law-{law_id}",
        "_source": "IL/KnessetOData",
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": law["Name"],
        "text": text,
        "date": pub_date,
        "url": pdf_url,
        "law_id": law_id,
        "knesset_num": law.get("KnessetNum"),
        "is_basic_law": law.get("IsBasicLaw", False),
        "is_budget_law": law.get("IsBudgetLaw"),
        "validity": law.get("LawValidityDesc"),
        "latest_publication_date": (law.get("LatestPublicationDate") or "").split("T")[0] or None,
    }


def fetch_all(max_laws: Optional[int] = None) -> Generator[dict, None, None]:
    """Yield all normalized law documents with full text."""
    skip = 0
    total_fetched = 0
    total_with_text = 0

    while True:
        print(f"Fetching laws {skip}–{skip + PAGE_SIZE}...", file=sys.stderr)
        laws = fetch_laws(skip=skip, top=PAGE_SIZE)
        if not laws:
            break

        for law in laws:
            law_id = law["IsraelLawID"]
            law_name = law["Name"][:60]
            total_fetched += 1

            if max_laws and total_fetched > max_laws:
                print(f"Reached max_laws={max_laws}", file=sys.stderr)
                return

            time.sleep(RATE_LIMIT_DELAY)
            docs = fetch_docs_for_law(law_id)
            if not docs:
                print(f"  [{total_fetched}] {law_name} — no documents", file=sys.stderr)
                continue

            # Try PDFs in order (most recent first)
            text = None
            pdf_url = None
            for doc in docs:
                fp = doc.get("FilePath")
                if not fp or not fp.lower().endswith(".pdf"):
                    continue
                time.sleep(RATE_LIMIT_DELAY)
                print(f"  [{total_fetched}] Downloading PDF for: {law_name}", file=sys.stderr)
                text = download_pdf_text(fp)
                if text:
                    pdf_url = fp
                    break

            if not text:
                print(f"  [{total_fetched}] {law_name} — no text extracted", file=sys.stderr)
                continue

            total_with_text += 1
            yield normalize(law, text, pdf_url)

        skip += PAGE_SIZE

    print(f"\nTotal: {total_fetched} laws, {total_with_text} with text",
          file=sys.stderr)


def bootstrap_sample(num_records: int = 15):
    """Fetch a sample of law documents and save to sample/."""
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    for record in fetch_all(max_laws=50):
        count += 1
        out_path = sample_dir / f"{record['_id']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"  Saved sample {count}: {record['title'][:60]}", file=sys.stderr)
        if count >= num_records:
            break

    print(f"\nSample complete: {count} documents saved to {sample_dir}",
          file=sys.stderr)
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IL/KnessetOData data fetcher")
    parser.add_argument("command", choices=["bootstrap"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch sample data only")
    parser.add_argument("--max-laws", type=int, default=None,
                        help="Maximum number of laws to process")
    args = parser.parse_args()

    if args.command == "bootstrap":
        if args.sample:
            bootstrap_sample()
        else:
            for record in fetch_all(max_laws=args.max_laws):
                print(json.dumps(record, ensure_ascii=False))
