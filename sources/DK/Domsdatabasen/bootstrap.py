#!/usr/bin/env python3
"""
DK/Domsdatabasen — Danish Court Decisions via HuggingFace Dataset

Fetches ~3,900 pseudonymized Danish court decisions from the
alexandrainst/domsdatabasen dataset on HuggingFace. Covers Supreme Court,
High Courts, Maritime & Commercial Court, district courts, and
Greenlandic courts since January 2022.

Dataset: https://huggingface.co/datasets/alexandrainst/domsdatabasen
Source: https://domsdatabasen.dk/
License: Open Data (public domain court decisions)
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

SOURCE_ID = "DK/Domsdatabasen"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"

# HuggingFace dataset viewer API
HF_API = "https://datasets-server.huggingface.co"
DATASET_ID = "alexandrainst/domsdatabasen"
CONFIG = "default"
SPLIT = "train"

# Page size for the rows endpoint
PAGE_SIZE = 100


def get_session() -> requests.Session:
    """Create a requests session with proper headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (research; https://github.com/ZachLaik/LegalDataHunter)",
        "Accept": "application/json",
    })
    return session


def clean_text(text: str) -> str:
    """Clean OCR-extracted text: normalize whitespace, strip anon tags."""
    if not text:
        return ""
    # Remove <anonym>...</anonym> wrapper but keep inner text
    text = re.sub(r"</?anonym>", "", text)
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def fetch_dataset_info(session: requests.Session) -> dict:
    """Fetch dataset metadata."""
    resp = session.get(f"{HF_API}/info", params={"dataset": DATASET_ID})
    resp.raise_for_status()
    return resp.json()


def fetch_rows(session: requests.Session, offset: int = 0, length: int = PAGE_SIZE) -> dict:
    """Fetch a page of rows from the dataset."""
    resp = session.get(
        f"{HF_API}/rows",
        params={
            "dataset": DATASET_ID,
            "config": CONFIG,
            "split": SPLIT,
            "offset": offset,
            "length": length,
        },
    )
    resp.raise_for_status()
    return resp.json()


def normalize(row: dict) -> Optional[dict]:
    """Normalize a dataset row into standard schema."""
    row_data = row.get("row", row)

    case_id = str(row_data.get("case_id", ""))
    if not case_id:
        return None

    # Use anonymized text (text_anon) for privacy, fall back to text
    raw_text = row_data.get("text_anon") or row_data.get("text") or ""
    text = clean_text(raw_text)
    if not text or len(text) < 50:
        return None

    title = row_data.get("Overskrift") or ""
    court = row_data.get("Ret") or ""
    case_number = row_data.get("Rettens sagsnummer") or ""
    case_type = row_data.get("Sagstype") or ""
    instance = row_data.get("Instans") or ""
    status = row_data.get("Afgørelsesstatus") or ""
    subject_group = row_data.get("Faggruppe") or ""
    topics = row_data.get("Sagsemner") or ""

    # Build title if empty
    if not title:
        title = f"{court} — {case_number}" if court and case_number else case_id

    # Extract date — try Afgørelsesdato first, then parse from text
    date_str = row_data.get("Afgørelsesdato") or ""
    date_iso = None
    if date_str:
        try:
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    date_iso = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    # Fall back to extracting date from text ("afsagt den 15. juni 2021")
    if not date_iso and text:
        danish_months = {
            "januar": "01", "februar": "02", "marts": "03", "april": "04",
            "maj": "05", "juni": "06", "juli": "07", "august": "08",
            "september": "09", "oktober": "10", "november": "11", "december": "12",
        }
        m = re.search(r"(?:afsagt|afsagt den|den)\s+(\d{1,2})\.\s+(\w+)\s+(\d{4})", text)
        if m:
            day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
            month_num = danish_months.get(month_name)
            if month_num:
                date_iso = f"{year}-{month_num}-{int(day):02d}"

    url = f"https://domsdatabasen.dk/#sag/{case_id}"

    return {
        "_id": f"DK/Domsdatabasen/{case_id}",
        "_source": SOURCE_ID,
        "_type": "case_law",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": date_iso,
        "url": url,
        "court": court,
        "case_number": case_number,
        "case_type": case_type,
        "instance": instance,
        "status": status,
        "subject_group": subject_group,
        "topics": topics,
        "language": "da",
    }


def fetch_all(session: requests.Session, limit: Optional[int] = None) -> Generator[dict, None, None]:
    """Yield all normalized records from the dataset."""
    offset = 0
    total_yielded = 0

    while True:
        if limit and total_yielded >= limit:
            break

        try:
            data = fetch_rows(session, offset=offset, length=PAGE_SIZE)
        except requests.HTTPError as e:
            print(f"  HTTP error at offset {offset}: {e}", file=sys.stderr)
            break

        rows = data.get("rows", [])
        if not rows:
            break

        for row in rows:
            if limit and total_yielded >= limit:
                break
            record = normalize(row)
            if record:
                total_yielded += 1
                yield record

        num_rows_total = data.get("num_rows_total", 0)
        offset += len(rows)

        if offset >= num_rows_total:
            break

        time.sleep(0.5)  # Be polite to HF API

    print(f"  Total records yielded: {total_yielded}", file=sys.stderr)


def fetch_updates(session: requests.Session, since: str) -> Generator[dict, None, None]:
    """Fetch updates — for HF datasets, re-fetch all (dataset is small)."""
    yield from fetch_all(session)


def bootstrap_sample(session: requests.Session, count: int = 15) -> list:
    """Fetch sample records for validation."""
    records = []
    for record in fetch_all(session, limit=count):
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description="DK/Domsdatabasen bootstrap")
    parser.add_argument("command", nargs="?", default="bootstrap",
                        choices=["bootstrap", "bootstrap-fast", "fetch-all", "fetch-updates"])
    parser.add_argument("--full", action="store_true", help="Full pull (default for non-sample)")
    parser.add_argument("--sample", action="store_true", help="Fetch sample records only")
    parser.add_argument("--since", type=str, help="ISO date for incremental fetch")
    parser.add_argument("--limit", type=int, default=None, help="Limit records")
    args, _unknown = parser.parse_known_args()

    session = get_session()

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample:
            SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
            records = bootstrap_sample(session, count=15)
            for i, rec in enumerate(records):
                path = SAMPLE_DIR / f"sample_{i:03d}.json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
                text_len = len(rec.get("text", ""))
                print(f"  [{i+1:2d}] {rec['_id']} — {text_len:,} chars — {rec.get('court', 'N/A')}")
            print(f"\nSaved {len(records)} samples to {SAMPLE_DIR}")
            # Validation summary
            texts = [len(r.get("text", "")) for r in records]
            avg_text = sum(texts) / len(texts) if texts else 0
            print(f"Avg text length: {avg_text:,.0f} chars")
            print(f"Min text length: {min(texts):,} chars")
            print(f"Max text length: {max(texts):,} chars")
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            out_path = DATA_DIR / "records.jsonl"
            count = 0
            with open(out_path, "w", encoding="utf-8") as f:
                for record in fetch_all(session, limit=args.limit):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
            print(f"Wrote {count} records to {out_path}")

    elif args.command == "fetch-all":
        for record in fetch_all(session, limit=args.limit):
            print(json.dumps(record, ensure_ascii=False))

    elif args.command == "fetch-updates":
        since = args.since or "2020-01-01"
        for record in fetch_updates(session, since):
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
