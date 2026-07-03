#!/usr/bin/env python3
"""
BJ/CourConstitutionnelle — Benin Constitutional Court Decisions

Fetches decisions from the Cour Constitutionnelle du Bénin (courconstitutionnelle.bj).

Strategy:
  - Listing pages by year and decision type (DCC, EL, EP, EG), paginated (?page=N)
  - Each listing yields decision URLs and PDF URLs
  - Download PDF → extract full text via PyMuPDF

Data:
  - ~4000+ DCC decisions spanning 1993–2026
  - Additional EL, EP, EG electoral decisions
  - Full text in French (PDF with mostly selectable text)
  - License: Public Domain (Government Works)

Usage:
  python3 bootstrap.py bootstrap          # Full initial pull
  python3 bootstrap.py bootstrap --sample # Fetch 15 sample records
"""

import io
import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://courconstitutionnelle.bj"
DELAY = 1.5
HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
}

# Decision type categories with their URL slugs
DECISION_TYPES = {
    "decisions-ordinaires-dcc": "DCC",
    "decisions-electorales-legislatives-el": "EL",
    "decisions-electorales-presidentielles-ep": "EP",
    "decisions-electorales-generales-eg": "EG",
}

# Years to scan (Constitutional Court created 1990, first decisions ~1993)
YEARS = list(range(2026, 1992, -1))

FRENCH_MONTHS = {
    "janvier": "01", "fevrier": "02", "février": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "août": "08", "aout": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "décembre": "12", "decembre": "12",
}

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    logger.warning("PyMuPDF (fitz) not available — trying pypdf fallback")
    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None
        logger.warning("pypdf not available either — PDF extraction disabled")


def _get(url: str, timeout: int = 30) -> Optional[str]:
    """GET a URL and return response text."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"GET {url} failed: {e}")
        return None


def _download_pdf(url: str) -> Optional[bytes]:
    """Download a PDF file."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        logger.warning(f"PDF download failed {url}: {e}")
        return None


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    raw = ""
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                raw += page.get_text()
            doc.close()
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed: {e}")
            return ""
    elif PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                raw += (page.extract_text() or "")
        except Exception as e:
            logger.warning(f"pypdf extraction failed: {e}")
            return ""
    else:
        return ""
    return _clean_text(raw)


def _clean_text(text: str) -> str:
    """Clean extracted PDF text: remove HTML tags, collapse noise lines."""
    # Strip any HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove lines that are just single characters or OCR noise (short non-word lines)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip very short lines that are just OCR artifacts (single chars, symbols)
        if len(stripped) <= 2 and not stripped.isdigit():
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _parse_french_date(date_str: str) -> Optional[str]:
    """Parse a French date like '12 décembre 2025' to ISO format."""
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str.strip())
    if not m:
        return None
    day, month_fr, year = m.groups()
    month_num = FRENCH_MONTHS.get(month_fr.lower())
    if not month_num:
        return None
    return f"{year}-{month_num}-{day.zfill(2)}"


def list_decisions_for_year_type(type_slug: str, year: int) -> List[Dict[str, str]]:
    """Get all decisions for a given year and type by paginating."""
    all_decisions = []
    page = 1

    while True:
        url = f"{BASE_URL}/fr/decision-type/{type_slug}/{year}"
        if page > 1:
            url += f"?page={page}"

        html = _get(url)
        if not html:
            break

        # Check total count on first page
        if page == 1:
            total_match = re.search(r"Total\s*:\s*(\d+)", html)
            total = int(total_match.group(1)) if total_match else 0
            if total == 0:
                break

        # Extract decision links and PDF links
        detail_links = re.findall(
            r'href="(https://courconstitutionnelle\.bj/fr/decisions/([^"]+))"', html
        )
        pdf_links = re.findall(
            r'href="(https://courconstitutionnelle\.bj/files/decisions/([^"]+\.pdf))"', html
        )

        # Extract dates from the HTML context
        date_matches = re.findall(
            r"((?:DCC|EL|EP|EG)\d{2}-\d+)\s+du\s+(\d{1,2}\s+\w+\s+\d{4})", html
        )

        # Build a map of case_number -> date
        date_map = {}
        for case_num, date_str in date_matches:
            date_map[case_num] = date_str

        # Build a map of case_number -> pdf_url
        pdf_map = {}
        for pdf_url, pdf_name in pdf_links:
            case_match = re.match(r"((?:DCC|EL|EP|EG)\d{2}-\d+)", pdf_name)
            if case_match:
                pdf_map[case_match.group(1)] = pdf_url

        # Deduplicate decision links
        seen = set()
        for detail_url, case_num in detail_links:
            if case_num not in seen:
                seen.add(case_num)
                all_decisions.append({
                    "case_number": case_num,
                    "detail_url": detail_url,
                    "pdf_url": pdf_map.get(case_num, ""),
                    "date_str": date_map.get(case_num, ""),
                })

        # Check if there are more pages
        next_pages = re.findall(r"page=(\d+)", html)
        max_page = max(int(p) for p in next_pages) if next_pages else page
        if page >= max_page:
            break
        page += 1
        time.sleep(DELAY)

    return all_decisions


def list_decisions_from_main(max_pages: int = 745) -> List[Dict[str, str]]:
    """Get decisions from the main paginated listing (most efficient)."""
    all_decisions = []

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/fr/decisions?page={page}"
        html = _get(url)
        if not html:
            break

        # Extract decision links and PDF links
        detail_links = re.findall(
            r'href="https://courconstitutionnelle\.bj/fr/decisions/([^"]+)"[^>]*class="btn btn-sm btn-primary', html
        )
        pdf_links = re.findall(
            r'href="(https://courconstitutionnelle\.bj/files/decisions/([^"]+\.pdf))"', html
        )

        # Extract titles with dates: "EP26-002 du 23 avril 2026"
        titles = re.findall(
            r'<h4[^>]*>\s*(?:<[^>]+>\s*)*([A-Z]+-?\d{2}-\d+)\s+du\s+(\d{1,2}\s+\w+\s+\d{4})', html
        )

        # Build PDF map
        pdf_map = {}
        for pdf_url, pdf_name in pdf_links:
            case_match = re.match(r"([A-Z]+-?\d{2}-\d+)", pdf_name)
            if case_match:
                pdf_map[case_match.group(1)] = pdf_url

        # Build records — derive type from case number prefix
        seen = set()
        for case_num, date_str in titles:
            if case_num in seen:
                continue
            seen.add(case_num)
            # Derive type from prefix: DCC, EL, EP, EG
            type_code = re.match(r"([A-Z]+)", case_num).group(1) if re.match(r"([A-Z]+)", case_num) else "DCC"
            all_decisions.append({
                "case_number": case_num,
                "detail_url": f"{BASE_URL}/fr/decisions/{case_num}",
                "pdf_url": pdf_map.get(case_num, f"{BASE_URL}/files/decisions/{case_num}_{date_str.replace(' ', '_')}.pdf"),
                "date_str": date_str,
                "type_code": type_code,
            })

        if not titles:
            break

        logger.info(f"Page {page}: {len(titles)} decisions (total: {len(all_decisions)})")
        time.sleep(DELAY)

    return all_decisions


def list_all_decisions(sample: bool = False) -> List[Dict[str, str]]:
    """Get all decisions across all types and years."""
    if sample:
        # For sample mode, use main listing (faster — 2 pages = 20 decisions)
        return list_decisions_from_main(max_pages=2)

    # For full mode, use main listing too (simpler than year/type iteration)
    return list_decisions_from_main()


def normalize(raw: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Normalize a raw record into the standard schema."""
    date_iso = _parse_french_date(raw.get("date_str", "")) if raw.get("date_str") else None

    return {
        "_id": f"BJ-CC-{raw['case_number']}",
        "_source": "BJ/CourConstitutionnelle",
        "_type": "case_law",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": f"Décision {raw['case_number']}",
        "text": text,
        "date": date_iso,
        "url": raw.get("detail_url", ""),
        "pdf_url": raw.get("pdf_url", ""),
        "case_number": raw["case_number"],
        "decision_type": raw.get("type_code", ""),
    }


def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Yield all normalized records with full text."""
    items = list_all_decisions(sample=sample)
    logger.info(f"Total decisions to fetch: {len(items)}")

    if sample:
        items = items[:15]
        logger.info("Sample mode: limiting to 15 records")

    for i, item in enumerate(items):
        logger.info(f"[{i+1}/{len(items)}] Fetching {item['case_number']}")

        text = ""
        if item.get("pdf_url"):
            pdf_bytes = _download_pdf(item["pdf_url"])
            if pdf_bytes:
                text = _extract_text_from_pdf(pdf_bytes)
                logger.info(f"  Extracted {len(text)} chars from PDF")
            else:
                logger.warning(f"  PDF download failed")
        else:
            logger.warning(f"  No PDF URL for {item['case_number']}")

        if not text:
            logger.warning(f"  No text extracted for {item['case_number']}, skipping")
            continue

        record = normalize(item, text)
        yield record
        time.sleep(DELAY)


def bootstrap(sample: bool = False):
    """Run bootstrap.

    Sample mode: write per-record JSON files into sample/ for validation.
    Full mode: stream one JSON object per line into data/records.jsonl
               (valid JSONL — the ingest loader reads it line-by-line).
    """
    src_dir = Path(__file__).parent

    if sample:
        sample_dir = src_dir / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        all_records = []
        for record in fetch_all(sample=True):
            count += 1
            fname = sample_dir / f"record_{count:04d}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            all_records.append(record)
            logger.info(f"  Saved {fname.name}: {record['case_number']}")

        if all_records:
            combined = sample_dir / "all_samples.json"
            with open(combined, "w", encoding="utf-8") as f:
                json.dump(all_records, f, ensure_ascii=False, indent=2)

        logger.info(f"Bootstrap (sample) complete: {count} records saved to {sample_dir}")

        texts = [r.get("text", "") for r in all_records]
        non_empty = sum(1 for t in texts if len(t) > 100)
        logger.info(f"Validation: {non_empty}/{count} records have substantial text (>100 chars)")
        return count

    # Full mode: stream to data/records.jsonl as proper JSONL (one object per line).
    data_dir = src_dir / "data"
    data_dir.mkdir(exist_ok=True)
    jsonl_path = data_dir / "records.jsonl"

    count = 0
    seen_ids = set()
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in fetch_all(sample=False):
            rid = record.get("_id")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if count % 100 == 0:
                logger.info(f"Progress: {count} records written")

    logger.info(f"Bootstrap (full) complete: {count} unique records -> {jsonl_path}")
    return count


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("bootstrap", "bootstrap-fast"):
        sample_flag = "--sample" in args
        bootstrap(sample=sample_flag)
    else:
        print("Usage: python3 bootstrap.py bootstrap|bootstrap-fast [--sample]")
        sys.exit(1)
