#!/usr/bin/env python3
"""
Belize Financial Services Commission — Laws & Amendments

Fetches financial services legislation from belizefsc.org.bz using the
WordPress REST API v2. PDFs are downloaded and text extracted via pdfplumber.

WP categories used (legislation-related):
  62  Acts (laws-amendment)
  65  Accounting Records Act
  70  Money Laundering & Terrorism Prevention
  83  Other Legislation Act
  93  International Money Lending SI
  98  International Foundation SI
  99  International Limited Liability Companies SI
  100 Mutual Administrative Assistance SI
  142 Economic Substance
  147 High Seas Fishing
  153 Companies
  155 Business Names
  156 Companies (statutory instrument)
  158 Limited Liability Partnerships
  161 International Business Companies
  162 Intellectual Property Assets
  169 Financial Services Commission
  170 Securities Industry (laws-amendment)
  291 Movable Assets
  298 International Merchant Marine Registry
  305 Insolvency and Bankruptcy
"""

import html
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SOURCE_ID = "BZ/FSC-Legislation"
BASE_URL = "https://www.belizefsc.org.bz"
API_URL = f"{BASE_URL}/wp-json/wp/v2"

# WP category IDs that contain legislation
LEGISLATION_CATEGORIES = [
    62, 65, 70, 83, 93, 98, 99, 100, 142, 147, 153, 155, 156,
    158, 161, 162, 169, 170, 291, 298, 305,
]

# Title keywords that indicate actual legislation (not press releases, forms, etc.)
LAW_KEYWORDS = re.compile(
    r'\b(act|regulation|rules|order|statutory instrument|'
    r'si no|code|amendment|consolidated)\b', re.IGNORECASE
)


def curl_get(url: str, max_attempts: int = 3, timeout: int = 30) -> Optional[str]:
    """GET via curl with retries."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', str(timeout),
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-H', 'Accept: application/json, text/html',
                 url],
                capture_output=True, text=True, timeout=timeout + 10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except subprocess.TimeoutExpired:
            pass
        delay = min(5 * (2 ** attempt), 30)
        logger.warning(f"GET attempt {attempt + 1} failed for {url}, waiting {delay}s")
        time.sleep(delay)
    return None


def curl_download(url: str, dest: str, max_attempts: int = 3) -> bool:
    """Download a file via curl."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '60',
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-o', dest, url],
                capture_output=True, text=True, timeout=70
            )
            if result.returncode == 0 and os.path.getsize(dest) > 100:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
        delay = min(5 * (2 ** attempt), 30)
        logger.warning(f"Download attempt {attempt + 1} failed for {url}")
        time.sleep(delay)
    return False


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"PDF extraction failed for {pdf_path}: {e}")
        return ""


def fetch_category_posts(category_ids: List[int], per_page: int = 100) -> List[Dict]:
    """Fetch all posts from given WP categories."""
    all_posts = []
    seen_ids = set()
    cats_str = ",".join(str(c) for c in category_ids)

    page = 1
    while True:
        url = f"{API_URL}/posts?categories={cats_str}&per_page={per_page}&page={page}"
        logger.info(f"Fetching page {page}: {url}")
        raw = curl_get(url)
        if not raw:
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break
        if not isinstance(data, list) or len(data) == 0:
            break
        for post in data:
            pid = post.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(post)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(1.5)

    return all_posts


def extract_pdf_urls(content_html: str) -> List[str]:
    """Extract PDF URLs from WP post content HTML."""
    urls = re.findall(r'(?:href|data)="([^"]*\.pdf[^"]*)"', content_html)
    return list(dict.fromkeys(urls))  # deduplicate, preserve order


def is_legislation(title: str, categories: List[int]) -> bool:
    """Check if a post is actual legislation vs press release/form/notice."""
    if LAW_KEYWORDS.search(title):
        return True
    # Posts in the core "Acts" category (62) or SI categories
    core_cats = {62, 93, 98, 99, 100, 156, 170, 298, 305}
    if set(categories) & core_cats:
        return True
    return False


def normalize(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a raw post+PDF record into standard schema."""
    title = html.unescape(raw.get("title", ""))
    text = raw.get("text", "")
    if not text or len(text) < 50:
        return None

    date_str = raw.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    return {
        "_id": f"bz-fsc-{raw['post_id']}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": date_str or None,
        "url": raw.get("url", ""),
        "pdf_url": raw.get("pdf_url", ""),
        "category": raw.get("category", ""),
        "wp_post_id": raw.get("post_id"),
    }


def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all legislation documents with full text from PDFs."""
    # Also fetch category mapping for labels
    cat_map = {}
    raw_cats = curl_get(f"{API_URL}/categories?per_page=100")
    if raw_cats:
        try:
            for c in json.loads(raw_cats):
                cat_map[c["id"]] = c["slug"]
        except (json.JSONDecodeError, KeyError):
            pass

    posts = fetch_category_posts(LEGISLATION_CATEGORIES)
    logger.info(f"Fetched {len(posts)} posts from legislation categories")

    # Filter to actual legislation
    legislation_posts = []
    for p in posts:
        title = html.unescape(p.get("title", {}).get("rendered", ""))
        cat_ids = p.get("categories", [])
        content = p.get("content", {}).get("rendered", "")
        pdf_urls = extract_pdf_urls(content)
        if not pdf_urls:
            continue
        if not is_legislation(title, cat_ids):
            logger.debug(f"Skipping non-legislation: {title}")
            continue
        legislation_posts.append((p, title, cat_ids, pdf_urls))

    logger.info(f"Found {len(legislation_posts)} legislation posts with PDFs")

    if sample:
        legislation_posts = legislation_posts[:15]

    count = 0
    for p, title, cat_ids, pdf_urls in legislation_posts:
        post_id = p["id"]
        date = p.get("date", "")
        link = p.get("link", "")
        cat_slug = cat_map.get(cat_ids[0], "") if cat_ids else ""

        # Try each PDF URL until we get text
        text = ""
        used_pdf = ""
        for pdf_url in pdf_urls:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                if curl_download(pdf_url, tmp_path):
                    text = extract_pdf_text(tmp_path)
                    if text and len(text) >= 50:
                        used_pdf = pdf_url
                        break
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            time.sleep(1.0)

        if not text or len(text) < 50:
            logger.warning(f"No text extracted for post {post_id}: {title}")
            continue

        raw = {
            "post_id": post_id,
            "title": title,
            "date": date,
            "url": link,
            "pdf_url": used_pdf,
            "text": text,
            "category": cat_slug,
        }

        record = normalize(raw)
        if record:
            count += 1
            logger.info(f"[{count}] {title[:60]} ({len(text)} chars)")
            yield record
            time.sleep(1.5)

    logger.info(f"Total records: {count}")


def save_samples(records: List[Dict], sample_dir: Path):
    """Save sample records to JSON files."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        fname = re.sub(r'[^\w\-]', '_', r["_id"])[:80] + ".json"
        path = sample_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Saved {len(records)} samples to {sample_dir}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="BZ/FSC-Legislation bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Fetch legislation")
    boot.add_argument("--sample", action="store_true", help="Sample mode (15 docs)")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    fast = sub.add_parser("bootstrap-fast", help="Quick sample fetch")

    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_mode = getattr(args, "sample", False) or args.command == "bootstrap-fast"
        sample_dir = Path(__file__).parent / "sample"
        records = []
        for record in fetch_all(sample=sample_mode):
            records.append(record)
        if records:
            save_samples(records, sample_dir)
            print(f"SUCCESS: {len(records)} records with full text")
        else:
            print("ERROR: No records fetched")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
