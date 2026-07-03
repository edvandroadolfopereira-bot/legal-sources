#!/usr/bin/env python3
"""
AU/NSWCaselaw — New South Wales Caselaw (all NSW courts & tribunals).

NSW Caselaw (https://www.caselaw.nsw.gov.au/) is the official database of
judgments and decisions of the New South Wales courts and tribunals — the
Court of Appeal, Court of Criminal Appeal, Supreme Court, District Court,
Land and Environment Court, NCAT and others. Every decision page already
contains the FULL judgment text.

Data access strategy:
  - The full corpus is mirrored as an openly redistributable, ungated
    HuggingFace dataset (corto-ai/nsw-caselaw, ~27,453 decisions) that was
    harvested directly from caselaw.nsw.gov.au. Each row carries the full
    plain-text judgment plus citation, court/jurisdiction, date and the
    canonical decision id.
  - We read it through the HuggingFace datasets-server rows API (no auth,
    no IP blocking, paginated) and reconstruct the canonical
    https://www.caselaw.nsw.gov.au/decision/<id> URL for every record.

Why not scrape caselaw.nsw.gov.au directly: the site is reachable but only
exposes per-decision HTML behind a session-driven search UI; the curated
dataset gives the same full text in clean, paginated form.

License: Copyright in Judicial Decisions Notice 1995 (NSW). Copyright in NSW
judicial decisions resides in the State, but the Notice authorises ANY person
to "reproduce, publish and otherwise deal with" any judicial decision, so long
as third-party law-report editorial material (headnotes etc.) is not copied.
The judgment bodies published here are the courts' own text — commercial reuse
with attribution is permitted.

Usage:
  python bootstrap.py test                 # connectivity check
  python bootstrap.py bootstrap --sample   # write 15 sample records to sample/
  python bootstrap.py bootstrap --full     # write all records to data/records.jsonl
  python bootstrap.py bootstrap-fast       # alias for --full (VPS runner)
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AU.NSWCaselaw")

SOURCE_ID = "AU/NSWCaselaw"
HF_ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "corto-ai/nsw-caselaw"
CONFIG = "default"
SPLIT = "train"
PAGE_SIZE = 100

DECISION_URL = "https://www.caselaw.nsw.gov.au/decision/{id}"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"

# Map the dataset's "type" to a coarse court label for the title prefix.
_CITATION_COURT_RE = re.compile(r"\[\d{4}\]\s+([A-Z]+)")


def _clean_text(text: str) -> str:
    """Normalise whitespace; the source text is already plain text."""
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_date(value: str) -> Optional[str]:
    """Dataset dates look like '2024-02-22 00:00:00' -> '2024-02-22'."""
    if not value:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value.strip())
    return m.group(1) if m else None


def _decision_id(version_id: str) -> str:
    """'nsw_caselaw:18dcdadf1e3b6911ffdedb20' -> '18dcdadf1e3b6911ffdedb20'."""
    if not version_id:
        return ""
    return version_id.split(":", 1)[-1].strip()


class NSWCaselawScraper:
    """Scraper for the official NSW Caselaw corpus via the HuggingFace mirror."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def _fetch_batch(self, offset: int, length: int) -> dict:
        params = {
            "dataset": DATASET,
            "config": CONFIG,
            "split": SPLIT,
            "offset": offset,
            "length": length,
        }
        last_err = None
        for attempt in range(5):
            try:
                resp = self.session.get(HF_ROWS_API, params=params, timeout=60)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # transient 502/timeout from datasets-server
                last_err = e
                logger.warning(f"Batch {offset} attempt {attempt + 1} failed: {e}")
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch batch at offset {offset}: {last_err}")

    def fetch_all(self) -> Generator[dict, None, None]:
        offset = 0
        total = None
        while True:
            data = self._fetch_batch(offset, PAGE_SIZE)
            if total is None:
                total = data.get("num_rows_total", 0)
                logger.info(f"Total decisions in dataset: {total}")
            rows = data.get("rows", [])
            if not rows:
                break
            for item in rows:
                record = self.normalize(item.get("row", {}))
                if record:
                    yield record
            offset += len(rows)
            logger.info(f"  ... processed {offset}/{total}")
            if total and offset >= total:
                break
            time.sleep(1)

    def fetch_updates(self, since: Optional[datetime] = None) -> Generator[dict, None, None]:
        """Static snapshot dataset — no incremental feed."""
        logger.info("Static dataset snapshot; no incremental updates available.")
        return
        yield

    def normalize(self, raw: dict) -> Optional[dict]:
        text = _clean_text(raw.get("text") or "")
        if not text or len(text) < 200:
            return None

        version_id = (raw.get("version_id") or "").strip()
        dec_id = _decision_id(version_id)
        citation = (raw.get("citation") or "").strip()
        date = _parse_date(raw.get("date") or "")

        if dec_id:
            doc_id = f"AU-NSW-{dec_id}"
            url = DECISION_URL.format(id=dec_id)
        else:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            doc_id = f"AU-NSW-{digest}"
            url = (raw.get("url") or "https://www.caselaw.nsw.gov.au/").strip()

        title = citation or (text.split("\n", 1)[0][:150].strip())

        return {
            "_id": doc_id,
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url,
            "citation": citation,
            "jurisdiction": (raw.get("jurisdiction") or "new_south_wales").strip(),
            "court_code": _court_from_citation(citation),
            "doc_type": (raw.get("type") or "decision").strip(),
            "word_count": raw.get("word_count"),
            "language": "en",
        }

    def test(self) -> bool:
        try:
            data = self._fetch_batch(0, 1)
            total = data.get("num_rows_total", 0)
            rows = data.get("rows", [])
            if not rows:
                print("FAIL: no rows returned")
                return False
            rec = self.normalize(rows[0].get("row", {}))
            print(f"OK: dataset has {total} decisions")
            print(f"Sample id: {rec['_id']}  citation: {rec['citation']}")
            print(f"Text length: {len(rec['text']):,} chars; url: {rec['url']}")
            return True
        except Exception as e:
            print(f"FAIL: {e}")
            return False


def _court_from_citation(citation: str) -> str:
    m = _CITATION_COURT_RE.search(citation or "")
    return m.group(1) if m else ""


def main():
    parser = argparse.ArgumentParser(description="AU/NSWCaselaw data fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Fetch a small sample (15 records)")
    parser.add_argument("--full", action="store_true", help="Fetch all records to data/records.jsonl")
    args = parser.parse_args()

    scraper = NSWCaselawScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)
        return

    if args.command == "update":
        logger.info("Static dataset; nothing to update.")
        return

    full = args.full or args.command == "bootstrap-fast"
    if args.sample:
        full = False

    if full:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / "records.jsonl"
        count = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for record in scraper.fetch_all():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                if count % 500 == 0:
                    logger.info(f"  ... {count} records written")
        logger.info(f"Bootstrap complete: {count} records -> {out_path}")
        return

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    max_records = 15
    for record in scraper.fetch_all():
        out_path = SAMPLE_DIR / f"record_{count:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[{count + 1}] {record.get('citation', '?')[:60]} "
            f"({len(record.get('text', '')):,} chars)"
        )
        count += 1
        if count >= max_records:
            break
    logger.info(f"Bootstrap complete: {count} records saved to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
