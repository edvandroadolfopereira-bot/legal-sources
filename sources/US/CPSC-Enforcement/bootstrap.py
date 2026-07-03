#!/usr/bin/env python3
"""
US/CPSC-Enforcement -- Consumer Product Safety Commission Recalls & Enforcement

Fetches CPSC product recall records via the SaferProducts.gov REST API.
~9,800+ recall actions with descriptions, hazard info, and remedy details.

Data access:
  - REST API at saferproducts.gov/RestWebServices/Recall (no auth)
  - Returns JSON (add format=json parameter)
  - Query by date range: RecallDateStart, RecallDateEnd

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
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional, Dict, Any, List

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.CPSC-Enforcement")

API_URL = "https://www.saferproducts.gov/RestWebServices/Recall"
DELAY = 1.5
SOURCE_ID = "US/CPSC-Enforcement"


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


class CPSCScraper:
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self.session = get_session()

    def _fetch_batch(self, start_date: str, end_date: str) -> Optional[List[Dict]]:
        """Fetch recalls for a date range. Dates in YYYY-MM-DD format."""
        params = {
            "format": "json",
            "RecallDateStart": start_date,
            "RecallDateEnd": end_date,
        }
        for attempt in range(3):
            try:
                resp = self.session.get(API_URL, params=params, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    return []
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning("Rate limited, waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                logger.warning("HTTP %d from API (%s to %s)", resp.status_code, start_date, end_date)
                return None
            except requests.RequestException as e:
                logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                time.sleep(5)
        return None

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        recall_id = str(raw.get("RecallID", ""))
        recall_number = str(raw.get("RecallNumber", ""))
        title = raw.get("Title", "") or ""
        description = raw.get("Description", "") or ""

        # Combine text from multiple fields
        hazards = []
        for h in (raw.get("Hazards") or []):
            name = h.get("Name", "")
            if name:
                hazards.append(name)
        hazard_text = "; ".join(hazards)

        remedies = []
        for r in (raw.get("Remedies") or []):
            name = r.get("Name", "")
            if name:
                remedies.append(name)
        remedy_text = "; ".join(remedies)

        consumer_contact = raw.get("ConsumerContact", "") or ""

        # Build full text
        parts = []
        if description:
            parts.append(description)
        if hazard_text:
            parts.append(f"Hazards: {hazard_text}")
        if remedy_text:
            parts.append(f"Remedies: {remedy_text}")
        if consumer_contact:
            parts.append(f"Consumer Contact: {consumer_contact}")
        text = "\n\n".join(parts)

        # Extract products info
        products = []
        for p in (raw.get("Products") or []):
            name = p.get("Name", "")
            if name:
                products.append(name)

        # Extract manufacturers
        manufacturers = []
        for m in (raw.get("Manufacturers") or []):
            name = m.get("Name", "")
            if name:
                manufacturers.append(name)

        # Extract manufacturer countries
        mfr_countries = []
        for mc in (raw.get("ManufacturerCountries") or []):
            country = mc.get("Country", "")
            if country:
                mfr_countries.append(country)

        # Parse date
        recall_date = raw.get("RecallDate", "")
        date = recall_date[:10] if recall_date and len(recall_date) >= 10 else None

        url = raw.get("URL", "")

        return {
            "_id": f"CPSC-{recall_number}" if recall_number else f"CPSC-{recall_id}",
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url or f"https://www.cpsc.gov/Recalls/{recall_number}",
            "recall_number": recall_number,
            "recall_id": recall_id,
            "products": "; ".join(products),
            "manufacturers": "; ".join(manufacturers),
            "manufacturer_countries": "; ".join(mfr_countries),
            "hazards": hazard_text,
            "remedies": remedy_text,
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict, None, None]:
        """Fetch all recalls in 6-month batches from 1973 to present."""
        count = 0
        target = 15 if sample else None

        if sample:
            # Just fetch recent records for sample
            end = datetime.now()
            start = end - timedelta(days=180)
            data = self._fetch_batch(
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
            )
            if data:
                logger.info("Sample batch: %d records", len(data))
                for raw in data:
                    record = self.normalize(raw)
                    if record["text"]:
                        yield record
                        count += 1
                        if count >= target:
                            return
            return

        # Full fetch: iterate in 6-month windows
        current_end = datetime.now()
        start_year = 1973  # CPSC was established in 1972

        while current_end.year >= start_year:
            current_start = current_end - timedelta(days=182)
            if current_start.year < start_year:
                current_start = datetime(start_year, 1, 1)

            start_str = current_start.strftime("%Y-%m-%d")
            end_str = current_end.strftime("%Y-%m-%d")

            data = self._fetch_batch(start_str, end_str)
            if data:
                logger.info("Batch %s to %s: %d records", start_str, end_str, len(data))
                for raw in data:
                    record = self.normalize(raw)
                    if record["text"]:
                        yield record
                        count += 1
            else:
                logger.warning("No data for %s to %s", start_str, end_str)

            current_end = current_start - timedelta(days=1)
            time.sleep(DELAY)

        logger.info("Completed: %d total records", count)

    def fetch_updates(self, since: str) -> Generator[Dict, None, None]:
        """Fetch recalls since a given date."""
        end = datetime.now().strftime("%Y-%m-%d")
        data = self._fetch_batch(since, end)
        count = 0
        if data:
            for raw in data:
                record = self.normalize(raw)
                if record["text"]:
                    yield record
                    count += 1
        logger.info("Update: %d records since %s", count, since)


def main():
    if len(sys.argv) < 2:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv or command == "bootstrap-fast"

    scraper = CPSCScraper()

    if command == "test":
        end = datetime.now()
        start = end - timedelta(days=30)
        data = scraper._fetch_batch(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if data:
            print(f"OK — API reachable. {len(data)} recalls in last 30 days.")
            if data:
                rec = scraper.normalize(data[0])
                print(f"Sample: {rec['title'][:80]}")
                print(f"Text length: {len(rec['text'])} chars")
        else:
            print("FAIL — could not reach SaferProducts API")
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
