#!/usr/bin/env python3
"""
Peshawar High Court — Reported Judgments fetcher (PK/PHC).

Source: Peshawar High Court Case Flow Management System (PHCCMS), the official
reported-judgments database of the Peshawar High Court (the constitutional High
Court for Khyber Pakhtunkhwa province, Pakistan).

Discovery: the reported-judgments page is a POST search form
(/PHCCMS/reportedJudgments.php?action=search) accepting `year`, `category`,
and `judge` filters. Each result row links a full-text judgment PDF under
/PHCCMS/judgments/<file>.pdf. We POST one request per year, parse the result
table, then download and text-extract each judgment PDF.

Full text is extracted from the judgment PDFs with pdfplumber.

Usage:
    python bootstrap.py bootstrap --sample   # ~12 sample records
    python bootstrap.py bootstrap            # all reported judgments -> data/records.jsonl
    python bootstrap.py bootstrap-fast --sample   # VPS pipeline alias
    python bootstrap.py updates --since 2024-01-01
"""

import argparse
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
from bs4 import BeautifulSoup

BASE_URL = "https://www.peshawarhighcourt.gov.pk"
SEARCH_URL = f"{BASE_URL}/PHCCMS/reportedJudgments.php?action=search"
LISTING_URL = f"{BASE_URL}/PHCCMS/reportedJudgments.php"

RATE_LIMIT = 1.5  # seconds between PDF downloads
MIN_TEXT_CHARS = 300  # skip image-only/scanned PDFs with no extractable text
SAMPLE_TARGET = 12
USER_AGENT = (
    "LegalDataHunter/1.0 (research project; "
    "+https://github.com/ZachLaik/LegalDataHunter)"
)

CATEGORY_NAMES = {
    "1": "Criminal",
    "2": "Civil",
    "3": "Revenue",
    "4": "Constitutional",
    "5": "Service",
    "6": "Corporate",
}


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    return session


def available_years() -> list[int]:
    """Year options offered by the search form (2010 .. current)."""
    current = datetime.now(timezone.utc).year
    return list(range(current, 2009, -1))


def parse_date(date_str: str) -> Optional[str]:
    """Parse a DD-MM-YYYY / DD.MM.YYYY judgment date to ISO YYYY-MM-DD."""
    if not date_str:
        return None
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", date_str)
    if m:
        day, month, year = m.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            return None
    m = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", date_str)
    if m:
        year, month, day = m.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def extract_case_number(title: str) -> Optional[str]:
    """Extract a case reference like 'W.P No. 2428-P of 2023' from the title cell."""
    if not title:
        return None
    m = re.match(
        r"\s*([A-Za-z][A-Za-z./ ]*?\.?\s*No\.?\s*[-\w./]+(?:\s+of\s+\d{4})?)",
        title,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def fetch_year_rows(session: requests.Session, year: int) -> list[dict]:
    """POST the search form for one year and parse the result rows."""
    data = {
        "year": str(year),
        "category": "0",
        "judge": "0",
        "form": "",
        "txtsearchbyremarks": "",
        "submit": "Search",
    }
    resp = session.post(SEARCH_URL, data=data, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for tr in soup.find_all("tr"):
        link = None
        for a in tr.find_all("a", href=True):
            if ".pdf" in a["href"].lower():
                link = a["href"]
                break
        if not link:
            continue
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue

        title = tds[1].get_text(" ", strip=True)
        headnote = tds[2].get_text(" ", strip=True)
        date_iso = parse_date(tds[5].get_text(" ", strip=True))
        category = tds[7].get_text(" ", strip=True)

        pdf_url = link if link.startswith("http") else BASE_URL + "/" + link.lstrip("/")
        # collapse the double slash the site emits (/PHCCMS//judgments/)
        pdf_url = re.sub(r"(?<!:)//+", "/", pdf_url)

        rows.append(
            {
                "case_title": title,
                "case_number": extract_case_number(title),
                "headnote": headnote,
                "date": date_iso,
                "category": category,
                "pdf_url": pdf_url,
                "year": year,
            }
        )
    return rows


def download_pdf_text(session: requests.Session, pdf_url: str) -> Optional[str]:
    """Download a judgment PDF and extract its text with pdfplumber."""
    try:
        resp = session.get(pdf_url, timeout=90)
        resp.raise_for_status()
        if "pdf" not in resp.headers.get("Content-Type", "").lower() and not resp.content[:4] == b"%PDF":
            return None
        parts = []
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        text = "\n".join(parts)
        # Normalize whitespace runs while preserving line structure
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception as e:  # noqa: BLE001
        print(f"  ! PDF error {pdf_url}: {e}", file=sys.stderr)
        return None


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def normalize(raw: dict, text: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    pdf_stem = Path(raw["pdf_url"].split("/")[-1]).stem
    ident = raw.get("case_number") or pdf_stem
    return {
        "_id": f"PK/PHC/{_slug(ident)[:120]}",
        "_source": "PK/PHC",
        "_type": "case_law",
        "_fetched_at": now,
        "title": raw.get("case_title", "").strip(),
        "case_number": raw.get("case_number"),
        "text": text,
        "date": raw.get("date"),
        "url": raw["pdf_url"],
        "court": "Peshawar High Court",
        "jurisdiction": "PK-KP",
        "country": "PK",
        "language": "en",
        "category": raw.get("category"),
        "headnote": raw.get("headnote") or None,
        "year": raw.get("year"),
    }


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    session = get_session()
    years = available_years()
    if sample:
        # Recent years are most reliably text-based (not scanned).
        years = [y for y in years if y <= datetime.now(timezone.utc).year][:4]

    seen = set()
    count = 0
    for year in years:
        try:
            rows = fetch_year_rows(session, year)
        except Exception as e:  # noqa: BLE001
            print(f"Error fetching year {year}: {e}", file=sys.stderr)
            continue
        print(f"Year {year}: {len(rows)} listed judgments", file=sys.stderr)

        for raw in rows:
            if sample and count >= SAMPLE_TARGET:
                return
            key = raw["pdf_url"]
            if key in seen:
                continue
            seen.add(key)

            time.sleep(RATE_LIMIT)
            text = download_pdf_text(session, raw["pdf_url"])
            if not text or len(text) < MIN_TEXT_CHARS:
                print(
                    f"  skip (no/low text): {raw.get('case_number') or raw['pdf_url']}",
                    file=sys.stderr,
                )
                continue

            record = normalize(raw, text)
            count += 1
            print(
                f"  [{count}] {record['_id']} ({len(text)} chars)",
                file=sys.stderr,
            )
            yield record

        if sample and count >= SAMPLE_TARGET:
            return


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
    parser = argparse.ArgumentParser(description="Fetch Peshawar High Court judgments")
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
