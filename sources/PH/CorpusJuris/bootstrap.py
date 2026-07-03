#!/usr/bin/env python3
"""
PH/CorpusJuris -- Corpus Juris Free Philippine Law Database

Fetches Philippine legislation (Republic Acts, Presidential Decrees, Acts,
Batas Pambansa, Commonwealth Acts) and Supreme Court jurisprudence from
thecorpusjuris.com.

Strategy:
  - Legislative index pages list all documents per category (single page each)
  - Jurisprudence year pages (1901-1910) list cases with links
  - Each document page has full text in itemprop="articleBody" div
  - Dates from article:published_time meta or <time datetime="">

Usage:
  python bootstrap.py bootstrap --sample   # Fetch ~15 sample records
  python bootstrap.py bootstrap             # Full extraction
  python bootstrap.py test-api              # Test connectivity
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib3
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE_ID = "PH/CorpusJuris"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"
DATA_DIR = SOURCE_DIR / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PH.CorpusJuris")

BASE_URL = "https://thecorpusjuris.com"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (legal data research; +https://github.com/ZachLaik/LegalDataHunter)",
    "Accept": "text/html,application/xhtml+xml",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.verify = False

# Legislative categories: (slug, index_path, link_pattern, doc_type_label)
LEGISLATION_CATEGORIES = [
    ("republic-acts", "/legislative/republic-acts/", r'ra-no-[^"]+\.php', "Republic Act"),
    ("presidential-decrees", "/legislative/presidential-decrees/", r'pd-no-[^"]+\.php', "Presidential Decree"),
    ("acts", "/legislative/acts/", r'act-no-[^"]+\.php', "Act"),
    ("batas-pambansa", "/legislative/batas-pambansa/", r'bp-blg-[^"]+\.php', "Batas Pambansa"),
    ("commonwealth-acts", "/legislative/commonwealth-acts/", r'ca-no-[^"]+\.php', "Commonwealth Act"),
]

# Jurisprudence years with CMS pages containing case links
JURIS_YEARS = list(range(1901, 1911))


def clean_html(html_text: str) -> str:
    """Remove HTML tags and clean up text."""
    if not html_text:
        return ""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def fetch_page(url: str) -> Optional[str]:
    """Fetch an HTML page with retry logic."""
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
            else:
                logger.warning(f"Failed to fetch {url}: {e}")
                return None
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None


def extract_text(html: str) -> str:
    """Extract full text from itemprop='articleBody' or fallback."""
    # Primary: itemprop="articleBody"
    m = re.search(r'itemprop="articleBody"[^>]*>(.*)', html, re.DOTALL | re.IGNORECASE)
    if m:
        # Take everything until the closing div at the same level
        content = m.group(1)
        # Find where the articleBody div ends (look for the pattern of
        # closing div followed by structural elements)
        # Strategy: take content up to the alert/sidebar/feature-box/footer
        for end_pat in [
            r'<div\s+class="alert\s',
            r'<div\s+class="col-md-[46]',
            r'<div\s+class="feature-box',
            r'<hr\s',
            r'<footer',
            r'<div\s+class="row">\s*<div\s+class="col-md-6',
        ]:
            end_m = re.search(end_pat, content, re.IGNORECASE)
            if end_m:
                content = content[:end_m.start()]
                break
        text = clean_html(content)
        if len(text) > 100:
            return text

    # Fallback: body minus nav/footer
    body = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL | re.IGNORECASE)
    if body:
        content = body.group(1)
        for tag in ['header', 'nav', 'footer', 'aside']:
            content = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', content, flags=re.DOTALL | re.IGNORECASE)
        text = clean_html(content)
        if len(text) > 100:
            return text

    return ""


def extract_title(html: str) -> str:
    """Extract document title from <title> or <h1>."""
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if title_match:
        title = clean_html(title_match.group(1)).strip()
        title = re.sub(r'\s*[•|–-]\s*(The\s+)?Corpus\s+Juris.*$', '', title, flags=re.IGNORECASE)
        if title and len(title) > 3:
            return title
    for tag in ['h1', 'h2']:
        h_match = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', html, re.DOTALL | re.IGNORECASE)
        if h_match:
            t = clean_html(h_match.group(1)).strip()
            if t and len(t) > 3:
                return t
    return "Untitled Document"


def extract_date(html: str) -> Optional[str]:
    """Extract date from structured metadata."""
    # article:published_time
    m = re.search(r'article:published_time"\s+content="([^"]+)"', html)
    if m:
        raw = m.group(1).strip()
        try:
            dt = datetime.strptime(raw[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    # <time datetime="">
    m2 = re.search(r'<time[^>]*datetime="([^"]+)"', html)
    if m2:
        raw = m2.group(1).strip()
        try:
            dt = datetime.strptime(raw[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def scrape_index_links(index_url: str, link_pattern: str) -> list:
    """Scrape an index page for document links matching a pattern."""
    html = fetch_page(index_url)
    if not html:
        return []
    matches = re.findall(rf'href="({link_pattern})"', html, re.IGNORECASE)
    seen = set()
    links = []
    for href in matches:
        full_url = urljoin(index_url, href)
        if full_url not in seen:
            seen.add(full_url)
            links.append(full_url)
    return links


def scrape_juris_year(year: int) -> list:
    """Get case links from a jurisprudence year page."""
    url = f"{BASE_URL}/judiciary/jurisprudence/{year}/"
    html = fetch_page(url)
    if not html:
        return []
    matches = re.findall(r'href="([^"]*(?:gr-no|am-no|oc-no|ac-no)[^"]*\.php)"', html, re.IGNORECASE)
    seen = set()
    links = []
    for href in matches:
        full_url = urljoin(url, href)
        if full_url not in seen:
            seen.add(full_url)
            links.append(full_url)
    return links


def doc_id_from_url(url: str, category: str) -> str:
    """Create a unique _id from URL."""
    fname = url.rstrip('/').split('/')[-1].replace('.php', '')
    return f"PH/CorpusJuris/{category}/{fname}"


def format_doc_number(url: str, doc_type: str) -> str:
    """Extract a human-readable document number from the URL."""
    fname = url.rstrip('/').split('/')[-1].replace('.php', '')
    prefix_map = {
        "Republic Act": ("ra-no-", "R.A. No. "),
        "Presidential Decree": ("pd-no-", "P.D. No. "),
        "Act": ("act-no-", "Act No. "),
        "Batas Pambansa": ("bp-blg-", "B.P. Blg. "),
        "Commonwealth Act": ("ca-no-", "C.A. No. "),
    }
    if doc_type in prefix_map:
        raw_prefix, nice_prefix = prefix_map[doc_type]
        num = fname.replace(raw_prefix, '')
        return f"{nice_prefix}{num}"
    # Case law
    fname_upper = fname.upper()
    if 'GR-NO' in fname_upper:
        num = re.sub(r'^GR-NO-', '', fname_upper)
        return f"G.R. No. {num}"
    if 'AM-NO' in fname_upper:
        num = re.sub(r'^AM-NO-', '', fname_upper)
        return f"A.M. No. {num}"
    return fname


def fetch_document(url: str, category: str, doc_type: str, data_type: str) -> Optional[dict]:
    """Fetch and normalize a single document."""
    html = fetch_page(url)
    if not html:
        return None

    text = extract_text(html)
    if not text or len(text) < 100:
        return None

    title = extract_title(html)
    date = extract_date(html)
    doc_num = format_doc_number(url, doc_type)

    record = {
        "_id": doc_id_from_url(url, category),
        "_source": SOURCE_ID,
        "_type": data_type,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": date,
        "url": url,
        "document_number": doc_num,
        "document_type": doc_type,
    }
    return record


def fetch_legislation(limit: int = 0) -> Generator[dict, None, None]:
    """Fetch legislation across all categories."""
    total = 0
    for slug, index_path, link_pattern, doc_type in LEGISLATION_CATEGORIES:
        if limit and total >= limit:
            return
        index_url = f"{BASE_URL}{index_path}"
        logger.info(f"Scraping {doc_type} index from {index_url}")
        links = scrape_index_links(index_url, link_pattern)
        logger.info(f"  Found {len(links)} {doc_type} documents")

        for url in links:
            if limit and total >= limit:
                return
            time.sleep(1.5)
            record = fetch_document(url, slug, doc_type, "legislation")
            if record:
                total += 1
                logger.info(f"  [{total}] {record['document_number']}: {record['title'][:60]}... ({len(record['text'])} chars)")
                yield record


def fetch_jurisprudence(limit: int = 0) -> Generator[dict, None, None]:
    """Fetch Supreme Court decisions from available years (1901-1910)."""
    total = 0
    for year in JURIS_YEARS:
        if limit and total >= limit:
            return
        logger.info(f"Scraping jurisprudence for {year}...")
        links = scrape_juris_year(year)
        if not links:
            continue
        logger.info(f"  Found {len(links)} cases for {year}")

        for url in links:
            if limit and total >= limit:
                return
            time.sleep(1.5)
            record = fetch_document(url, "cases", "Supreme Court Decision", "case_law")
            if record:
                total += 1
                logger.info(f"  [{total}] {record['document_number']}: {record['title'][:60]}... ({len(record['text'])} chars)")
                yield record


def fetch_all() -> Generator[dict, None, None]:
    yield from fetch_legislation()
    yield from fetch_jurisprudence()


def fetch_updates(since: str) -> Generator[dict, None, None]:
    yield from fetch_legislation()


def normalize(raw: dict) -> dict:
    return raw


def save_samples(records: list):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for rec in records:
        fname = re.sub(r'[^a-zA-Z0-9_-]', '_', rec["_id"].split("/")[-1])[:80] + ".json"
        path = SAMPLE_DIR / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(records)} sample records to {SAMPLE_DIR}")


def test_api():
    logger.info("Testing connectivity to thecorpusjuris.com...")

    # Test Republic Acts index
    links = scrape_index_links(f"{BASE_URL}/legislative/republic-acts/", r'ra-no-[^"]+\.php')
    logger.info(f"  Republic Acts index: {len(links)} links found")
    if not links:
        logger.error("  FAILED: no Republic Act links found")
        return False

    # Test individual RA page with full text extraction
    html = fetch_page(links[0])
    if html:
        text = extract_text(html)
        title = extract_title(html)
        date = extract_date(html)
        logger.info(f"  RA page: {title[:60]}... ({len(text)} chars, date={date})")
    else:
        logger.error("  FAILED: could not fetch RA page")
        return False

    # Test jurisprudence
    case_links = scrape_juris_year(1901)
    logger.info(f"  Jurisprudence 1901: {len(case_links)} cases found")
    if case_links:
        html = fetch_page(case_links[0])
        if html:
            text = extract_text(html)
            logger.info(f"  Case page: {len(text)} chars")

    logger.info("All connectivity tests passed!")
    return True


def bootstrap(sample: bool = False):
    if sample:
        logger.info("Running in SAMPLE mode — fetching ~15 records")
        records = []

        # Get 8 legislation samples (first 2 from each available category)
        logger.info("Fetching legislation samples...")
        for rec in fetch_legislation(limit=8):
            records.append(rec)

        # Get 7 jurisprudence samples
        logger.info("Fetching jurisprudence samples...")
        for rec in fetch_jurisprudence(limit=7):
            records.append(rec)

        if records:
            save_samples(records)
            logger.info(f"Bootstrap sample complete: {len(records)} records")
            texts = [r.get("text", "") for r in records]
            avg_len = sum(len(t) for t in texts) / len(texts) if texts else 0
            empty = sum(1 for t in texts if len(t) < 100)
            logger.info(f"  Average text length: {avg_len:.0f} chars")
            logger.info(f"  Empty/short texts: {empty}/{len(records)}")
        else:
            logger.error("No records fetched!")
            sys.exit(1)
    else:
        logger.info("Running FULL bootstrap")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        jsonl_path = DATA_DIR / "records.jsonl"
        count = 0
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for rec in fetch_all():
                rec = normalize(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
                if count % 100 == 0:
                    logger.info(f"Progress: {count} records written")
        logger.info(f"Full bootstrap complete: {count} records -> {jsonl_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PH/CorpusJuris bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "test-api"])
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    if args.command == "test-api":
        success = test_api()
        sys.exit(0 if success else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        bootstrap(sample=args.sample)
