#!/usr/bin/env python3
"""
INTL/LeXFiles -- 5.8M English legal documents from 6 jurisdictions (HuggingFace)

11 sub-corpora: EU legislation (93K), EU court cases (29K), ECtHR (12K),
UK legislation (52K), UK courts (47K), Indian courts (34K),
Canadian legislation (6K), Canadian courts (11K), US courts (4.6M),
US legislation (518), US contracts (622K).

Streams from HuggingFace — no auth required.

Usage:
  python bootstrap.py bootstrap            # Full initial pull (stdout JSONL)
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast       # Alias for bootstrap
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import json
import logging
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.LeXFiles")

DATASET_ID = "lexlms/lex_files"
SPLIT = "train"

# Map URL domains to jurisdiction + document type
DOMAIN_TYPE_MAP = {
    "www.ontariocourts.ca": ("CA", "case_law"),
    "www.canlii.org": ("CA", "case_law"),
    "canlii.ca": ("CA", "case_law"),
    "www.scc-csc.ca": ("CA", "case_law"),
    "decisions.scc-csc.ca": ("CA", "case_law"),
    "laws-lois.justice.gc.ca": ("CA", "legislation"),
    "laws.justice.gc.ca": ("CA", "legislation"),
    "www.laws-lois.justice.gc.ca": ("CA", "legislation"),
    "eur-lex.europa.eu": ("EU", "legislation"),
    "curia.europa.eu": ("EU", "case_law"),
    "hudoc.echr.coe.int": ("CoE", "case_law"),
    "www.legislation.gov.uk": ("GB", "legislation"),
    "www.bailii.org": ("GB", "case_law"),
    "bailii.org": ("GB", "case_law"),
    "indiankanoon.org": ("IN", "case_law"),
    "www.courtlistener.com": ("US", "case_law"),
    "courtlistener.com": ("US", "case_law"),
    "storage.courtlistener.com": ("US", "case_law"),
    "www.law.cornell.edu": ("US", "legislation"),
    "law.cornell.edu": ("US", "legislation"),
    "www.govinfo.gov": ("US", "legislation"),
    "www.sec.gov": ("US", "legislation"),
    "efts.sec.gov": ("US", "legislation"),
}


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    if not url:
        return ""
    try:
        # Handle URLs with or without scheme
        if "://" in url:
            return url.split("://", 1)[1].split("/", 1)[0].lower()
        return url.split("/", 1)[0].lower()
    except Exception:
        return ""


def extract_title(text: str, max_len: int = 200) -> str:
    """Extract a title from the first meaningful lines of text."""
    if not text:
        return "Untitled Document"
    lines = text.strip().split("\n")
    # Skip empty lines, find first non-trivial line
    for line in lines[:10]:
        cleaned = line.strip()
        if len(cleaned) > 5 and not cleaned.startswith(("http", "---", "===")):
            title = cleaned[:max_len]
            if len(cleaned) > max_len:
                title = title.rsplit(" ", 1)[0] + "..."
            return title
    return "Untitled Document"


def make_doc_id(url: str, text: str, index: int) -> str:
    """Generate a stable document ID from text content hash."""
    # Use text content for uniqueness (many records share the same URL)
    content = text[:2000] if text else f"{url}:{index}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_date(created_ts: str) -> Optional[str]:
    """Parse created_timestamp into ISO date. Handles 'YYYY' or 'MM-DD-YYYY' etc."""
    if not created_ts:
        return None
    created_ts = str(created_ts).strip()
    # Try YYYY format
    if re.match(r"^\d{4}$", created_ts):
        return f"{created_ts}-01-01"
    # Try YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}", created_ts):
        return created_ts[:10]
    # Try MM-DD-YYYY
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})", created_ts)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
    return None


def clean_text(text: str) -> str:
    """Clean document text: normalize whitespace, strip HTML artifacts."""
    if not text:
        return ""
    # Remove stray HTML tags if any
    text = re.sub(r"<[^>]{1,80}>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    return text.strip()


class LeXFilesScraper(BaseScraper):
    """Scraper for INTL/LeXFiles — multinational legal corpus from HuggingFace."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a HuggingFace record into standard schema."""
        text = clean_text(raw.get("text", ""))
        url = raw.get("url", "") or ""
        created = raw.get("created_timestamp", "") or ""
        index = raw.get("_index", 0)

        domain = extract_domain(url)
        jurisdiction, doc_type = DOMAIN_TYPE_MAP.get(domain, ("INTL", "legislation"))

        doc_id = make_doc_id(url, text, index)
        title = extract_title(text)
        date = parse_date(created)

        return {
            "_id": f"lexfiles-{doc_id}",
            "_source": "INTL/LeXFiles",
            "_type": doc_type,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date,
            "url": url,
            "jurisdiction": jurisdiction,
            "language": "en",
        }

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Stream all records from HuggingFace dataset."""
        from datasets import load_dataset

        logger.info("Loading dataset %s (split=%s) via streaming...", DATASET_ID, SPLIT)
        ds = load_dataset(DATASET_ID, split=SPLIT, streaming=True)

        count = 0
        for item in ds:
            raw = dict(item)
            raw["_index"] = count
            record = self.normalize(raw)
            if record.get("text") and len(record["text"]) > 50:
                yield record
                count += 1
                if count % 5000 == 0:
                    logger.info("Yielded %d records so far...", count)

        logger.info("Finished: yielded %d records total", count)

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Not applicable for a static dataset."""
        logger.info("Static dataset — fetch_updates returns nothing")
        return
        yield  # Make it a generator

    def test(self) -> bool:
        """Quick connectivity test."""
        try:
            from datasets import load_dataset
            ds = load_dataset(DATASET_ID, split=SPLIT, streaming=True)
            item = next(iter(ds))
            text = item.get("text", "")
            logger.info("Test OK: url='%s', %d chars text",
                        (item.get("url", "") or "")[:60], len(text))
            return bool(text)
        except Exception as e:
            logger.error("Test failed: %s", e)
            return False


def main():
    scraper = LeXFilesScraper()
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
