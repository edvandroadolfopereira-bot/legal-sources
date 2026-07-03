#!/usr/bin/env python3
"""
SS/NRA-TaxLaws -- South Sudan National Revenue Authority Tax Laws

Fetches tax, finance, and customs legislation from the NRA's Strapi CMS API
and extracts full text from PDFs.

API: https://cms.nra.gov.ss/resources (Strapi v3 REST)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Incremental update
"""

import sys
import json
import logging
import re
import io
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.SS.NRA-TaxLaws")

SOURCE_ID = "SS/NRA-TaxLaws"
CMS_BASE = "https://cms.nra.gov.ss"
RESOURCES_URL = f"{CMS_BASE}/resources"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (research; +https://legaldatahunter.com)",
    "Accept": "application/json",
}

SAMPLE_LIMIT = 15

# Resource types that contain legislation (vs job ads, speeches, etc.)
LEGAL_TYPES = {"taxation_act", "financial_act", "custom_act"}

# Some resources typed as "manuals" or "publications" are actually legislation
LEGAL_TITLE_PATTERNS = [
    r"(?i)\bact[\b,]",
    r"(?i)\bregulation",
    r"(?i)\bcustom",
    r"(?i)\btaxation",
    r"(?i)\bfinance\b",
    r"(?i)\bfinancial\b",
    r"(?i)\bSSRA act",
    r"(?i)\brevenue authority.*act",
]


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return _clean_text("\n\n".join(pages_text))
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return ""


def _is_legal_resource(resource: dict) -> bool:
    """Check if a resource is legislation (by type or title pattern)."""
    rtype = resource.get("type", "")
    if rtype in LEGAL_TYPES:
        return True
    title = resource.get("title", "")
    for pattern in LEGAL_TITLE_PATTERNS:
        if re.search(pattern, title):
            return True
    return False


def _parse_date(date_str: str) -> str:
    """Parse date strings like 'April 26, 2020' to ISO format."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


class SourceScraper(BaseScraper):
    """
    Scraper for: South Sudan NRA Tax Laws
    Country: SS
    URL: https://nra.gov.ss/resources

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url="",
            headers=HEADERS,
        )

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all legal documents with full text from PDF."""
        logger.info(f"Fetching resources from {RESOURCES_URL}")
        resp = self.client.get(RESOURCES_URL)
        resources = resp.json()
        logger.info(f"Total resources: {len(resources)}")

        legal = [r for r in resources if _is_legal_resource(r)]
        logger.info(f"Legal resources: {len(legal)}")

        for i, res in enumerate(legal):
            doc_info = res.get("document", {})
            if not doc_info or not doc_info.get("url"):
                logger.warning(f"No document URL for: {res.get('title')}")
                continue

            pdf_url = CMS_BASE + doc_info["url"]
            title = res.get("title", "").strip()
            date = _parse_date(res.get("date", ""))

            logger.info(f"[{i+1}/{len(legal)}] Downloading: {title}")
            time.sleep(1.5)

            try:
                pdf_resp = self.client.get(pdf_url)
                if pdf_resp.status_code != 200:
                    logger.warning(f"HTTP {pdf_resp.status_code} for {pdf_url}")
                    continue
                pdf_bytes = pdf_resp.content
            except Exception as e:
                logger.warning(f"Download failed: {e}")
                continue

            text = _extract_pdf_text(pdf_bytes)
            if not text or len(text) < 50:
                logger.warning(f"Insufficient text from {title}: {len(text)} chars")
                continue

            doc_id = hashlib.sha256(pdf_url.encode()).hexdigest()[:16]

            yield {
                "_id": f"ss-nra-{res['id']}-{doc_id}",
                "_source": SOURCE_ID,
                "_type": "legislation",
                "_fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "text": text,
                "date": date or None,
                "url": f"https://nra.gov.ss/resources",
                "pdf_url": pdf_url,
                "resource_type": res.get("type", ""),
                "pdf_size_bytes": len(pdf_bytes),
                "published_at": res.get("published_at", ""),
            }

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Small corpus — re-fetch all on update."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        return raw


def main():
    scraper = SourceScraper()
    args = sys.argv[1:]

    if not args:
        print("Usage: bootstrap.py [bootstrap|bootstrap-fast|update] [--sample]")
        sys.exit(1)

    command = args[0]
    sample = "--sample" in args or "--samples" in args

    if command in ("bootstrap", "bootstrap-fast"):
        records = []
        for rec in scraper.fetch_all():
            records.append(rec)
            if sample and len(records) >= SAMPLE_LIMIT:
                break

        if sample:
            sample_dir = Path(__file__).parent / "sample"
            sample_dir.mkdir(exist_ok=True)
            for rec in records:
                fname = re.sub(r"[^a-zA-Z0-9_-]", "_", rec["_id"]) + ".json"
                with open(sample_dir / fname, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(records)} sample records to {sample_dir}")
        else:
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logger.info(f"Wrote {len(records)} records to {jsonl_path}")

        logger.info(f"Total: {len(records)} records")
        for rec in records[:3]:
            logger.info(f"  {rec['title'][:60]} | text={len(rec.get('text',''))} chars")

    elif command == "update":
        logger.info("Small corpus — running full fetch")
        count = 0
        for rec in scraper.fetch_all():
            count += 1
        logger.info(f"Updated {count} records")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
