#!/usr/bin/env python3
"""
BA/OHR -- Bosnia OHR Laws Database

Fetches Bosnia and Herzegovina legislation from the Office of the High
Representative (OHR) at https://www.ohr.int/laws-of-bih/

Strategy:
  1. Crawl 12 category pages listing legislation
  2. Extract PDF links and metadata from HTML tables
  3. Download PDFs and extract text via pdfplumber
  4. Normalize into per-document records

Archive: ~504 PDFs across 12 categories (constitutions, criminal,
election, judicial, succession, human rights, public institutions,
public information, citizenship, taxation, police, defence).

License: Public domain (government legislation)

Usage:
  python bootstrap.py bootstrap --sample   # ~15 sample records
  python bootstrap.py bootstrap             # Full extraction
  python bootstrap.py bootstrap-fast        # Alias for bootstrap --sample
"""

import hashlib
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import unquote

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip3 install pdfplumber")
    sys.exit(1)

SOURCE_ID = "BA/OHR"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"
DATA_DIR = SOURCE_DIR / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("BA.OHR")

BASE_URL = "https://www.ohr.int"
INDEX_URL = f"{BASE_URL}/laws-of-bih/"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (legal data research; +https://github.com/ZachLaik/LegalDataHunter)",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

CRAWL_DELAY = 1.0

# Category page IDs and names
CATEGORIES = [
    (68220, "Constitutions"),
    (68240, "Criminal legislation"),
    (68222, "Election legislation"),
    (68243, "Judicial and prosecutorial system"),
    (68245, "Succession of the Former SFRY"),
    (68251, "Human rights"),
    (68253, "Public institutions"),
    (68255, "Public information"),
    (68258, "Citizenship and travel documents"),
    (68261, "Taxation and financial legislation"),
    (68265, "Police legislation"),
    (68270, "Defence legislation"),
]


def fetch(url: str, retries: int = 2, timeout: int = 30) -> Optional[requests.Response]:
    """Fetch a URL with retries."""
    for attempt in range(retries + 1):
        try:
            resp = SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
            else:
                logger.error(f"Failed to fetch {url}: {e}")
                return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
            try:
                page.flush_cache(); page.get_textmap.cache_clear()
            except Exception:
                pass
        pdf.close()
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning(f"PDF extraction error: {e}")
        return ""


def title_from_url(pdf_url: str) -> str:
    """Extract a readable title from a PDF URL."""
    filename = unquote(pdf_url.split("/")[-1])
    name = filename.replace(".pdf", "").replace("%20", " ")
    name = re.sub(r'[\-_]+', ' ', name)
    return name.strip()


def discover_pdfs(category_id: int, category_name: str) -> List[Dict[str, Any]]:
    """Get all PDF links from a category page."""
    url = f"{BASE_URL}/?page_id={category_id}"
    resp = fetch(url)
    if not resp:
        return []

    html = resp.text
    pdfs = []
    seen = set()

    for m in re.finditer(r'href="([^"]+\.pdf)"', html, re.I):
        pdf_url = m.group(1)
        if not pdf_url.startswith("http"):
            pdf_url = f"{BASE_URL}{pdf_url}"

        if pdf_url in seen:
            continue
        seen.add(pdf_url)

        # Try to extract context from surrounding HTML
        start = max(0, m.start() - 500)
        context = html[start:m.end() + 200]

        # Try to find link text
        link_text_match = re.search(
            r'<a[^>]*href="' + re.escape(m.group(1)) + r'"[^>]*>([^<]+)</a>',
            html
        )
        link_text = link_text_match.group(1).strip() if link_text_match else ""

        # Try to find gazette number from context
        gazette_match = re.search(r'(?:BH|RS|FBiH|BD),?\s*(\d+/\d+)', context)
        gazette = gazette_match.group(0) if gazette_match else ""

        # Try to find date
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', context)
        date_str = date_match.group(1) if date_match else ""

        title = link_text or title_from_url(pdf_url)

        pdfs.append({
            "pdf_url": pdf_url,
            "title": title,
            "category": category_name,
            "category_id": category_id,
            "gazette": gazette,
            "date_raw": date_str,
        })

    logger.info(f"Category '{category_name}': {len(pdfs)} PDFs")
    return pdfs


def parse_date(date_raw: str) -> Optional[str]:
    """Parse DD/MM/YYYY to ISO date."""
    if not date_raw:
        return None
    try:
        dt = datetime.strptime(date_raw, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw document record."""
    url_hash = hashlib.md5(raw["pdf_url"].encode()).hexdigest()[:10]
    return {
        "_id": f"BA-OHR-{url_hash}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": raw.get("title", ""),
        "text": raw.get("text", ""),
        "date": parse_date(raw.get("date_raw", "")),
        "url": raw.get("pdf_url", ""),
        "category": raw.get("category", ""),
        "gazette": raw.get("gazette", ""),
    }


def fetch_all(limit: Optional[int] = None) -> Iterator[Dict]:
    """Fetch all documents from all categories."""
    count = 0

    for cat_id, cat_name in CATEGORIES:
        if limit and count >= limit:
            return

        pdfs = discover_pdfs(cat_id, cat_name)
        time.sleep(CRAWL_DELAY)

        for pdf_info in pdfs:
            if limit and count >= limit:
                return

            resp = fetch(pdf_info["pdf_url"], timeout=60)
            time.sleep(CRAWL_DELAY)

            if not resp:
                continue

            ct = resp.headers.get("Content-Type", "")
            if "pdf" not in ct.lower() and not pdf_info["pdf_url"].lower().endswith(".pdf"):
                logger.warning(f"Not a PDF: {pdf_info['pdf_url']} (Content-Type: {ct})")
                continue

            text = extract_pdf_text(resp.content)
            if not text or len(text) < 100:
                logger.warning(f"Insufficient text from {pdf_info['pdf_url']}: {len(text)} chars")
                continue

            pdf_info["text"] = text
            record = normalize(pdf_info)
            yield record
            count += 1
            logger.info(f"[{count}] {record['title'][:70]} ({len(text)} chars)")

    logger.info(f"Total documents fetched: {count}")


def bootstrap(sample: bool = False):
    """Run the bootstrap process."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    limit = 15 if sample else None
    records = []

    for record in fetch_all(limit=limit):
        records.append(record)
        fname = SAMPLE_DIR / f"{record['_id']}.json"
        fname.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    if not sample:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        jsonl_path = DATA_DIR / "records.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info(f"Wrote {len(records)} records to {jsonl_path}")

    logger.info(f"Saved {len(records)} records to {SAMPLE_DIR}")

    if records:
        texts = [r["text"] for r in records if r.get("text")]
        avg_len = sum(len(t) for t in texts) / len(texts) if texts else 0
        logger.info(f"Average text length: {avg_len:.0f} chars")

    return records


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: python bootstrap.py bootstrap [--sample]")
        print("       python bootstrap.py bootstrap-fast")
        sys.exit(1)

    cmd = args[0]
    sample = "--sample" in args or cmd == "bootstrap-fast"

    if cmd in ("bootstrap", "bootstrap-fast"):
        records = bootstrap(sample=sample)
        print(f"Done. {len(records)} records.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
