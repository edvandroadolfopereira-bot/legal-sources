#!/usr/bin/env python3
"""
EG/EgyptianLawArticles-HF -- Egyptian Civil Code articles from HuggingFace

1,105 articles with full text in Arabic and English from TawasulAI dataset.
Streams from HuggingFace Parquet files.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import json
import logging
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
logger = logging.getLogger("legal-data-hunter.EG.EgyptianLawArticles-HF")

DATASET_ID = "TawasulAI/egyptian-law-articles"
SPLIT = "train"
SOURCE_ID = "EG/EgyptianLawArticles-HF"


class EgyptianLawArticlesHFScraper(BaseScraper):
    """Scraper for EG/EgyptianLawArticles-HF."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a HuggingFace record into standard schema."""
        # Use `or` fallbacks: dataset rows may carry present-but-None values,
        # in which case .get(key, default) returns None (not the default).
        articles = raw.get("articles") or {}
        number = str(articles.get("number") or "")
        text_ar = (articles.get("text_ar") or "").strip()
        text_en = (articles.get("text_en") or "").strip()

        # Combine Arabic and English text
        text_parts = []
        if text_ar:
            text_parts.append(text_ar)
        if text_en:
            text_parts.append(f"\n\n--- English Translation ---\n\n{text_en}")
        text = "".join(text_parts)

        title = f"Egyptian Civil Code — Article {number}" if number else "Egyptian Civil Code Article"

        return {
            "_id": f"{SOURCE_ID}:art-{number}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": None,
            "url": "https://huggingface.co/datasets/TawasulAI/egyptian-law-articles",
            "article_number": number,
            "language": "ar",
            "jurisdiction": "EG",
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
                if count % 200 == 0:
                    logger.info("Yielded %d records so far...", count)

        logger.info("Finished: yielded %d records total", count)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Not applicable for static dataset."""
        yield from self.fetch_all()

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            from datasets import load_dataset
            ds = load_dataset(DATASET_ID, split=SPLIT, streaming=True)
            item = next(iter(ds))
            articles = item.get("articles", {})
            text = articles.get("text_ar", "")
            logger.info("Test OK: article %s, %d chars Arabic text",
                        articles.get("number"), len(text))
            return bool(text)
        except Exception as e:
            logger.error("Test failed: %s", e)
            return False


def main():
    scraper = EgyptianLawArticlesHFScraper()
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

        if sample_mode:
            for record in scraper.fetch_all():
                out_file = sample_dir / f"record_{count:04d}.json"
                out_file.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                count += 1
                text_len = len(record.get("text", ""))
                logger.info("Sample %d: %s (%d chars)",
                            count, record.get("title", "")[:60], text_len)
                if limit and count >= limit:
                    break
        else:
            # Full mode: stream every record to data/records.jsonl so the VPS
            # ingest pipeline persists them (printing to stdout is NOT captured
            # as records — that left earlier runs with only the 15 samples).
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(exist_ok=True)
            out_path = data_dir / "records.jsonl"
            with open(out_path, "w", encoding="utf-8") as fh:
                for record in scraper.fetch_all():
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 200 == 0:
                        logger.info("Wrote %d records to %s", count, out_path)

        logger.info("Done: %d records %s",
                     count, "(sample)" if sample_mode else "(full)")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
