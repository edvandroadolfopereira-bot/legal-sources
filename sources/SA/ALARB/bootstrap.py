#!/usr/bin/env python3
"""
SA/ALARB -- Arabic Legal Argument Reasoning Benchmark (THIQAH-RD)

13,341 Saudi commercial court cases with structured case_facts, court_reasoning,
applicable_laws, and verdict. Streams from HuggingFace Parquet files.

Usage:
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap            # Full bootstrap (all records)
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import json
import hashlib
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
logger = logging.getLogger("legal-data-hunter.SA.ALARB")

DATASET_ID = "THIQAH-RD/ALARB"


class SAALARBScraper(BaseScraper):
    """Scraper for SA/ALARB — Saudi commercial court cases from HuggingFace."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def _clean_text(self, text: str) -> str:
        """Clean text: remove excessive whitespace."""
        if not text:
            return ""
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    def _join_array(self, arr) -> str:
        """Join a list of strings into a single text block."""
        if not arr:
            return ""
        if isinstance(arr, list):
            return "\n".join(str(item) for item in arr if item)
        return str(arr)

    def _generate_id(self, idx: int, verdict: str) -> str:
        """Generate a stable unique ID from index and verdict hash."""
        text_hash = hashlib.md5(verdict.encode('utf-8')).hexdigest()[:8]
        return f"alarb_{idx:05d}_{text_hash}"

    def normalize(self, raw: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
        """Transform a HuggingFace record into standard schema."""
        case_facts = self._join_array(raw.get("case_facts", []))
        court_reasoning = self._join_array(raw.get("court_reasoning", []))
        applicable_laws = self._join_array(raw.get("applicable_laws", []))
        verdict = self._clean_text(raw.get("verdict", ""))

        # Build full text from all structured fields
        parts = []
        if case_facts:
            parts.append("== وقائع الدعوى ==\n" + case_facts)
        if court_reasoning:
            parts.append("== أسباب الحكم ==\n" + court_reasoning)
        if applicable_laws:
            parts.append("== الأنظمة المطبقة ==\n" + applicable_laws)
        if verdict:
            parts.append("== المنطوق ==\n" + verdict)
        text = "\n\n".join(parts)

        # Title: first 120 chars of case facts
        title = case_facts[:120].strip() if case_facts else f"قضية تجارية #{idx}"

        record_id = self._generate_id(idx, verdict or str(idx))

        return {
            "_id": record_id,
            "_source": "SA/ALARB",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": None,
            "url": f"https://huggingface.co/datasets/THIQAH-RD/ALARB",
            "case_facts": case_facts,
            "court_reasoning": court_reasoning,
            "applicable_laws": applicable_laws,
            "verdict": verdict,
            "language": "ar",
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Stream all records from HuggingFace dataset (train + test splits)."""
        from datasets import load_dataset

        count = 0
        for split in ("train", "test"):
            logger.info("Loading dataset %s (split=%s) via streaming...", DATASET_ID, split)
            ds = load_dataset(DATASET_ID, split=split, streaming=True)

            for item in ds:
                record = self.normalize(dict(item), idx=count)
                if record.get("text"):
                    yield record
                    count += 1
                    if count % 2000 == 0:
                        logger.info("Yielded %d records so far...", count)

        logger.info("Finished: yielded %d records total", count)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Static dataset — fetch_updates returns all records."""
        yield from self.fetch_all()

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            from datasets import load_dataset
            ds = load_dataset(DATASET_ID, split="train", streaming=True)
            item = next(iter(ds))
            facts = item.get("case_facts", [])
            logger.info("Test OK: got record with %d case_facts entries", len(facts))
            return bool(facts)
        except Exception as e:
            logger.error("Test failed: %s", e)
            return False


def main():
    scraper = SAALARBScraper()
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
                            count, record.get("_id", "")[:40], text_len)
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
