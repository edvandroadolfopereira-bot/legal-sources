#!/usr/bin/env python3
"""
US/NHTSA-Enforcement -- NHTSA Defect Investigations (ODI)

Fetches NHTSA Office of Defects Investigation records via the public JSON API.
~4,100+ investigations with full-text descriptions covering vehicle safety
defect investigations, preliminary evaluations, and engineering analyses.

Data access:
  - JSON API at api.nhtsa.gov/investigations (no auth required)
  - Paginated with offset/max parameters
  - Returns HTML descriptions that are cleaned to plain text

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.NHTSA-Enforcement")

API_URL = "https://api.nhtsa.gov/investigations"
PAGE_SIZE = 50
DELAY = 1.5
SOURCE_ID = "US/NHTSA-Enforcement"

INVESTIGATION_TYPES = {
    "PE": "Preliminary Evaluation",
    "EA": "Engineering Analysis",
    "RQ": "Recall Query",
    "RD": "Recall Decision",
    "CL": "Closure",
    "MR": "Manufacturer Recall",
}

STATUS_LABELS = {
    "O": "Open",
    "C": "Closed",
    "MR": "Manufacturer Recall",
}


def clean_html(text: str) -> str:
    """Strip HTML tags and clean up whitespace."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    })
    return session


class NHTSAScraper:
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self.session = get_session()

    def _fetch_page(self, offset: int, max_results: int = PAGE_SIZE,
                    sort: str = "id", order: str = "desc") -> Optional[Dict]:
        params = {
            "offset": offset,
            "max": max_results,
            "sort": sort,
            "order": order,
        }
        for attempt in range(3):
            try:
                resp = self.session.get(API_URL, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning("Rate limited, waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                logger.warning("HTTP %d from API (offset=%d)", resp.status_code, offset)
                return None
            except requests.RequestException as e:
                logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                time.sleep(5)
        return None

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        nhtsa_id = raw.get("nhtsaId", "")
        inv_type_code = raw.get("investigationType", "")
        inv_type = INVESTIGATION_TYPES.get(inv_type_code, inv_type_code)
        status_code = raw.get("status", "")
        status_label = STATUS_LABELS.get(status_code, status_code)

        description = raw.get("description", "")
        text = clean_html(description) if description else ""

        subject = raw.get("subject", "")
        title = f"NHTSA {inv_type} {nhtsa_id}: {subject}" if subject else f"NHTSA {inv_type} {nhtsa_id}"

        open_date = raw.get("openDate", "")
        date = open_date[:10] if open_date and len(open_date) >= 10 else None

        return {
            "_id": nhtsa_id or str(raw.get("id", "")),
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": f"https://www.nhtsa.gov/vehicle/{nhtsa_id}" if nhtsa_id else None,
            "investigation_number": raw.get("investigationNumber", ""),
            "investigation_type": inv_type,
            "investigation_type_code": inv_type_code,
            "status": status_label,
            "status_code": status_code,
            "subject": subject,
            "nhtsa_id": nhtsa_id,
            "latest_activity_date": raw.get("latestActivityDate", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict, None, None]:
        offset = 0
        total = None
        count = 0
        target = 15 if sample else None

        while True:
            data = self._fetch_page(offset)
            if not data or "results" not in data:
                logger.error("No results at offset %d", offset)
                break

            results = data["results"]
            if not results:
                break

            if total is None:
                total = data.get("meta", {}).get("pagination", {}).get("total", "?")
                logger.info("Total investigations available: %s", total)

            for raw in results:
                record = self.normalize(raw)
                if record["text"]:
                    yield record
                    count += 1
                    if target and count >= target:
                        logger.info("Sample limit reached (%d records)", count)
                        return
                else:
                    logger.debug("Skipping record %s — empty text", record["_id"])

            offset += len(results)
            logger.info("Fetched %d records so far (offset=%d)", count, offset)

            if target and count >= target:
                return

            time.sleep(DELAY)

        logger.info("Completed: %d records fetched", count)

    def fetch_updates(self, since: str) -> Generator[Dict, None, None]:
        """Fetch investigations updated since a given date."""
        offset = 0
        count = 0

        while True:
            data = self._fetch_page(offset, sort="latestActivityDate", order="desc")
            if not data or "results" not in data:
                break

            results = data["results"]
            if not results:
                break

            past_cutoff = False
            for raw in results:
                activity_date = raw.get("latestActivityDate", "")[:10]
                if activity_date and activity_date < since:
                    past_cutoff = True
                    break
                record = self.normalize(raw)
                if record["text"]:
                    yield record
                    count += 1

            if past_cutoff:
                break

            offset += len(results)
            time.sleep(DELAY)

        logger.info("Update complete: %d new/updated records since %s", count, since)


def main():
    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv or command == "bootstrap-fast"

    scraper = NHTSAScraper()

    if command == "test":
        data = scraper._fetch_page(0, max_results=1)
        if data and data.get("results"):
            total = data["meta"]["pagination"]["total"]
            rec = scraper.normalize(data["results"][0])
            print(f"OK — API reachable. {total} investigations available.")
            print(f"Sample: {rec['title']}")
            print(f"Text length: {len(rec['text'])} chars")
        else:
            print("FAIL — could not reach NHTSA API")
            sys.exit(1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        jsonl_path = data_dir / "records.jsonl"

        records = []
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for record in scraper.fetch_all(sample=sample):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                records.append(record)

        # Save samples
        for i, record in enumerate(records[:15]):
            path = sample_dir / f"record_{i:04d}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

        logger.info("Saved %d records to %s", len(records), jsonl_path)
        logger.info("Saved %d samples to %s", min(len(records), 15), sample_dir)

        # Validation
        text_lengths = [len(r["text"]) for r in records if r.get("text")]
        if text_lengths:
            avg_len = sum(text_lengths) / len(text_lengths)
            logger.info("Text stats: min=%d, max=%d, avg=%d chars",
                        min(text_lengths), max(text_lengths), int(avg_len))

    elif command == "update":
        since = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
        for record in scraper.fetch_updates(since):
            print(json.dumps(record, ensure_ascii=False))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
