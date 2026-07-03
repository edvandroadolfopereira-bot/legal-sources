#!/usr/bin/env python3
"""
Balochistan Code — Provincial Legislation fetcher (PK/BalochistanCode).

Source: balochistancode.gob.pk, the official online code of the Balochistan
Law & Parliamentary Affairs Department (Government of Balochistan, Pakistan).
This completes the Pakistan provincial code set already covered for the other
provinces (Punjab, Sindh, Khyber Pakhtunkhwa).

Discovery: the alphabetical listing page
(/laws_rules.aspx?wise=alphabetical&opento=1) embeds an HTML-escaped blob of
~1,700 law entries, each linking a viewer URL of the form
/Document.aspx?wise=opendoc&docid=<N>&docc=<M>. The viewer page in turn exposes
the underlying full-text PDF at /lawdir/<uuid>.pdf. We parse the listing for
titles/metadata, resolve each viewer page to its PDF, then download and
text-extract the PDF with pdfplumber.

A minority of entries are legacy .doc uploads (the title ends in ".doc") whose
viewer does not yield a text-extractable PDF; those are skipped.

Usage:
    python bootstrap.py bootstrap --sample        # ~12 sample records
    python bootstrap.py bootstrap                 # all laws -> data/records.jsonl
    python bootstrap.py bootstrap-fast --sample   # VPS pipeline alias
    python bootstrap.py updates --since 2024-01-01
"""

import argparse
import html
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import pdfplumber
import requests

BASE_URL = "https://balochistancode.gob.pk"
LIST_URL = f"{BASE_URL}/laws_rules.aspx?wise=alphabetical&opento=1"

RATE_LIMIT = 1.5      # seconds between PDF/viewer fetches
MIN_TEXT_CHARS = 300  # skip image-only/scanned/empty PDFs
SAMPLE_TARGET = 12
TIMEOUT = 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "LegalDataHunter/1.0 (+https://github.com/ZachLaik/LegalDataHunter)"
)

DOC_RE = re.compile(
    r"Document\.aspx\?wise=opendoc&docid=(\d+)&docc=(\d+)'>(.*?)</a>",
    re.DOTALL,
)
SMALL_RE = re.compile(r"<small>(.*?)</small>", re.DOTALL)
LAWDIR_RE = re.compile(r"/lawdir/([0-9a-fA-F\-]+\.pdf)")


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-").lower()
    return s or "doc"


def _parse_date(text: str) -> Optional[str]:
    """Parse 'Promulgation Date: Fri Jul 12, 1963' -> '1963-07-12'."""
    m = re.search(r"Promulgation Date:\s*([A-Za-z]+ [A-Za-z]+ \d{1,2},\s*\d{4})", text)
    if not m:
        return None
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    for fmt in ("%a %b %d, %Y", "%A %b %d, %Y", "%a %B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_listing(page: str) -> list[dict]:
    """Extract law entries from the alphabetical listing page."""
    # The entry blob is HTML-escaped (sometimes doubly) inside the page markup.
    d = html.unescape(html.unescape(page))
    entries: list[dict] = []
    # Iterate doclist blocks so each <a> stays paired with its <small> metadata.
    for block in re.split(r"<div class=\"doclist\">", d)[1:]:
        m = DOC_RE.search(block)
        if not m:
            continue
        docid, docc, anchor = m.group(1), m.group(2), _clean(m.group(3))
        # Anchor text is "<Title> , <Year>"; trim trailing year and .doc/.pdf.
        title = anchor
        year = None
        ym = re.search(r",\s*(\d{4})\s*$", title)
        if ym:
            year = int(ym.group(1))
            title = title[: ym.start()].strip()
        title = re.sub(r"\.(doc|docx|pdf)\s*$", "", title, flags=re.IGNORECASE).strip()
        is_doc = bool(re.search(r"\.docx?\b", anchor, re.IGNORECASE))

        number = status = None
        sm = SMALL_RE.search(block)
        if sm:
            parts = [p.strip() for p in _clean(sm.group(1)).split("|")]
            # parts: [category, number, "Promulgation Date: ...", "Views: N", "Status: X"]
            if len(parts) >= 2 and parts[1] and not parts[1].lower().startswith("promulgation"):
                number = parts[1]
            for p in parts:
                if p.lower().startswith("status:"):
                    status = p.split(":", 1)[1].strip()
        date = _parse_date(block)

        entries.append({
            "docid": docid,
            "docc": docc,
            "viewer_url": f"{BASE_URL}/Document.aspx?wise=opendoc&docid={docid}&docc={docc}",
            "title": title,
            "year": year,
            "number": number,
            "status": status,
            "date": date,
            "is_doc": is_doc,
        })
    return entries


def resolve_pdf_url(session: requests.Session, viewer_url: str) -> Optional[str]:
    r = session.get(viewer_url, timeout=TIMEOUT)
    r.raise_for_status()
    m = LAWDIR_RE.search(r.text)
    if not m:
        return None
    return f"{BASE_URL}/lawdir/{m.group(1)}"


def download_pdf_text(session: requests.Session, pdf_url: str) -> str:
    r = session.get(pdf_url, timeout=TIMEOUT)
    r.raise_for_status()
    if "pdf" not in r.headers.get("Content-Type", "").lower() and not r.content[:4] == b"%PDF":
        return ""
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize(raw: dict, text: str, pdf_url: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id": f"PK/BalochistanCode/{raw['docid']}-{_slug(raw['title'])[:100]}",
        "_source": "PK/BalochistanCode",
        "_type": "legislation",
        "_fetched_at": now,
        "title": raw["title"],
        "text": text,
        "date": raw.get("date"),
        "url": raw["viewer_url"],
        "pdf_url": pdf_url,
        "number": raw.get("number"),
        "year": raw.get("year"),
        "status": raw.get("status"),
        "jurisdiction": "PK-BA",
        "country": "PK",
        "publisher": "Balochistan Law & Parliamentary Affairs Department",
        "language": "en",
    }


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    session = get_session()
    resp = session.get(LIST_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    entries = parse_listing(resp.text)
    print(f"Listing: {len(entries)} law entries", file=sys.stderr)

    count = 0
    seen: set[str] = set()
    for raw in entries:
        if sample and count >= SAMPLE_TARGET:
            return
        if raw["is_doc"]:
            continue  # legacy .doc uploads yield no extractable PDF
        try:
            time.sleep(RATE_LIMIT)
            pdf_url = resolve_pdf_url(session, raw["viewer_url"])
            if not pdf_url or pdf_url in seen:
                continue
            seen.add(pdf_url)
            text = download_pdf_text(session, pdf_url)
        except Exception as e:  # noqa: BLE001
            print(f"  error {raw['docid']}: {e}", file=sys.stderr)
            continue
        if not text or len(text) < MIN_TEXT_CHARS:
            print(f"  skip (no/low text): {raw['docid']} {raw['title'][:50]}", file=sys.stderr)
            continue
        record = normalize(raw, text, pdf_url)
        count += 1
        print(f"  [{count}] {record['_id']} ({len(text)} chars)", file=sys.stderr)
        yield record


def fetch_updates(since: str) -> Generator[dict, None, None]:
    since_date = datetime.fromisoformat(since.replace("Z", "+00:00"))
    if since_date.tzinfo is None:
        since_date = since_date.replace(tzinfo=timezone.utc)
    for record in fetch_all(sample=False):
        ds = record.get("date")
        if not ds:
            yield record
            continue
        try:
            if datetime.fromisoformat(ds).replace(tzinfo=timezone.utc) >= since_date:
                yield record
        except ValueError:
            yield record


def save_sample(records: list[dict], sample_dir: Path):
    sample_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        fname = record["_id"].replace("/", "_") + ".json"
        with open(sample_dir / fname, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"Saved: {sample_dir / fname}")


def main():
    parser = argparse.ArgumentParser(description="Fetch Balochistan Code provincial legislation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("bootstrap", "bootstrap-fast"):
        p = sub.add_parser(name)
        p.add_argument("--sample", action="store_true", help="Fetch only sample records")
    up = sub.add_parser("updates")
    up.add_argument("--since", required=True, help="ISO date (e.g. 2024-01-01)")

    args = parser.parse_args()
    script_dir = Path(__file__).parent
    sample_dir = script_dir / "sample"
    data_dir = script_dir / "data"

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample:
            records = list(fetch_all(sample=True))
            print(f"\nFetched {len(records)} sample records", file=sys.stderr)
            save_sample(records, sample_dir)
        else:
            data_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"
            count = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in fetch_all(sample=False):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 50 == 0:
                        print(f"Progress: {count} records written", file=sys.stderr)
            print(f"Full bootstrap complete: {count} records -> {jsonl_path}", file=sys.stderr)

    elif args.command == "updates":
        for record in fetch_updates(args.since):
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
