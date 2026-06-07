#!/usr/bin/env python3
"""
IL/CaseLawHF -- Israeli case law from HuggingFace dataset guychuk/case-law-israel

10,558 Israeli court judgments with full Hebrew text.
Streams from HuggingFace Parquet files — no large downloads needed.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import json
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.IL.CaseLawHF")

DATASET_ID = "guychuk/case-law-israel"
SPLIT = "judgments"

COURT_TYPE_MAP = {
    1: "Supreme Court",
    2: "District Court",
    3: "Magistrate Court",
    4: "Family Court",
    5: "Labor Court",
    6: "Labor Regional Court",
    7: "Military Court",
    8: "Military Appeals Court",
    9: "Administrative Court",
    10: "National Labor Court",
    11: "Other",
}

DISTRICT_MAP = {
    1: "Jerusalem",
    2: "Tel Aviv",
    3: "Haifa",
    4: "Central",
    5: "Southern (Be'er Sheva)",
    6: "Northern (Nazareth)",
    7: "National",
    8: "Other",
}


class ILCaseLawHFScraper(BaseScraper):
    """Scraper for IL/CaseLawHF — Israeli case law from HuggingFace."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def _clean_text(self, text: str) -> str:
        """Clean judgment text: remove excessive whitespace."""
        if not text:
            return ""
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    def _parse_judges(self, judges_str: str) -> list:
        """Parse judges from JSON string field."""
        if not judges_str:
            return []
        try:
            return json.loads(judges_str)
        except (json.JSONDecodeError, TypeError):
            return [judges_str] if judges_str else []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a HuggingFace record into standard schema."""
        judgment_id = raw.get("judgment_id", "")
        title = raw.get("title", "")
        case_number = raw.get("name_number", "")
        doc_date = raw.get("doc_create_date", "")
        court_code = raw.get("court_type_code")
        district_code = raw.get("district_code")
        text = self._clean_text(raw.get("document_text", ""))
        url_name = raw.get("url_name", "")
        judges = self._parse_judges(raw.get("judges_str", ""))

        court_type = COURT_TYPE_MAP.get(court_code, f"Unknown ({court_code})")
        district = DISTRICT_MAP.get(district_code, f"Unknown ({district_code})")

        url = f"https://www.nevo.co.il/psika_word/{url_name}" if url_name else ""

        return {
            "_id": judgment_id,
            "_source": "IL/CaseLawHF",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": doc_date if doc_date else None,
            "url": url,
            "case_number": case_number,
            "court_type": court_type,
            "district": district,
            "judges": judges,
            "language": "he",
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Stream all records from HuggingFace dataset."""
        from datasets import load_dataset

        logger.info("Loading dataset %s (split=%s) via streaming...", DATASET_ID, SPLIT)
        ds = load_dataset(DATASET_ID, split=SPLIT, streaming=True)

        count = 0
        for item in ds:
            record = self.normalize(dict(item))
            if record.get("text"):
                yield record
                count += 1
                if count % 500 == 0:
                    logger.info("Yielded %d records so far...", count)

        logger.info("Finished: yielded %d records total", count)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch records newer than `since` date."""
        for record in self.fetch_all():
            if record.get("date") and record["date"] >= since:
                yield record

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            from datasets import load_dataset
            ds = load_dataset(DATASET_ID, split=SPLIT, streaming=True)
            item = next(iter(ds))
            text = item.get("document_text", "")
            logger.info("Test OK: got record '%s' with %d chars text",
                        item.get("title", "")[:60], len(text))
            return bool(text)
        except Exception as e:
            logger.error("Test failed: %s", e)
            return False


def main():
    scraper = ILCaseLawHFScraper()
    args = sys.argv[1:]

    if not args:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample] [--full]")
        sys.exit(1)

    command = args[0]
    sample_mode = "--sample" in args

    if command == "test":
        ok = scraper.test()
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        limit = 15 if sample_mode else None
        count = 0
        for record in scraper.fetch_all():
            if sample_mode:
                out_file = sample_dir / f"{count:04d}.json"
                out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                count += 1
                text_len = len(record.get("text", ""))
                logger.info("Sample %d: %s (%d chars)",
                            count, record.get("title", "")[:60], text_len)
                if limit and count >= limit:
                    break
            else:
                print(json.dumps(record, ensure_ascii=False))
                count += 1

        logger.info("Done: %d records %s",
                     count, "(sample)" if sample_mode else "(full)")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
