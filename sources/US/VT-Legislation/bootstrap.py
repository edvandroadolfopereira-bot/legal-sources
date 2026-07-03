#!/usr/bin/env python3
"""
US/VT-Legislation -- Vermont Statutes Online

Fetches Vermont statutes from the official legislature site:
  https://legislature.vermont.gov/statutes/

Strategy:
  1. Enumerate all titles from the statutes index page
  2. For each title, enumerate chapters from the title page
  3. For each chapter, fetch full text via /statutes/fullchapter/XX/YYY
  4. Parse sections from HTML, concatenate into per-chapter records

Each record = one chapter (with all its sections concatenated).

Usage:
  python bootstrap.py bootstrap --sample   # ~15 sample chapters
  python bootstrap.py bootstrap             # Full extraction
  python bootstrap.py bootstrap-fast        # Alias for bootstrap --sample
"""

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

SOURCE_ID = "US/VT-Legislation"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"
DATA_DIR = SOURCE_DIR / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("US.VT-Legislation")

BASE_URL = "https://legislature.vermont.gov"
STATUTES_URL = f"{BASE_URL}/statutes/"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (legal data research; +https://github.com/ZachLaik/LegalDataHunter)",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

CRAWL_DELAY = 1.0


def strip_html(html_text: str) -> str:
    """Remove HTML tags and decode entities, returning clean text."""
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html_text, flags=re.DOTALL | re.I)
    text = re.sub(r'<br\s*/?>|</p>|</div>|</li>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()


def fetch(url: str, retries: int = 2) -> Optional[str]:
    """Fetch a URL with retries."""
    for attempt in range(retries + 1):
        try:
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
            else:
                logger.error(f"Failed to fetch {url}: {e}")
                return None


def discover_titles() -> List[str]:
    """Get all title codes from the statutes index and by probing."""
    title_codes = set()

    html = fetch(STATUTES_URL)
    if html:
        found = re.findall(r'href="/statutes/title/([^"]+)"', html)
        title_codes.update(found)

    # Titles 01-03 may not appear as links on the index — probe them
    for i in range(1, 34):
        code = f"{i:02d}"
        title_codes.add(code)

    # Known suffixed titles
    for suffix in ['09A', '11A', '11B', '11C', '14A', '15A', '15B', '15C', '27A',
                    '03APPENDIX', '10APPENDIX', '16APPENDIX', '24APPENDIX']:
        title_codes.add(suffix)

    result = sorted(title_codes, key=lambda x: (x.replace('APPENDIX', 'Z'), x))
    logger.info(f"Discovered {len(result)} titles")
    return result


def discover_chapters(title_code: str) -> List[Dict[str, str]]:
    """Get all chapters for a title."""
    url = f"{BASE_URL}/statutes/title/{title_code}"
    html = fetch(url)
    if not html:
        return []

    # Extract chapter links and names
    chapters = []
    seen = set()

    # Pattern: /statutes/chapter/XX/YYY with link text
    for m in re.finditer(
        r'href="/statutes/chapter/([^/]+)/(\d+)"[^>]*>([^<]*)</a>',
        html, re.I
    ):
        title_num, chap_num = m.group(1), m.group(2)
        chap_name = m.group(3).strip()
        key = f"{title_code}/{chap_num}"
        if key not in seen:
            seen.add(key)
            chapters.append({
                "title_code": title_code,
                "chapter_code": chap_num,
                "chapter_name": chap_name,
            })

    # Also try direct pattern without link text
    if not chapters:
        for m in re.finditer(r'href="/statutes/chapter/([^/]+)/(\d+)"', html, re.I):
            title_num, chap_num = m.group(1), m.group(2)
            key = f"{title_code}/{chap_num}"
            if key not in seen:
                seen.add(key)
                chapters.append({
                    "title_code": title_code,
                    "chapter_code": chap_num,
                    "chapter_name": "",
                })

    # Extract title name from page
    title_name_match = re.search(r'<h3[^>]*>\s*Title\s+\d+[A-Z]*\s*[:\-–—]?\s*([^<]+)', html, re.I)
    title_name = title_name_match.group(1).strip() if title_name_match else ""

    for ch in chapters:
        ch["title_name"] = title_name

    return chapters


def fetch_chapter_text(title_code: str, chapter_code: str) -> Optional[str]:
    """Fetch the full text of a chapter."""
    url = f"{BASE_URL}/statutes/fullchapter/{title_code}/{chapter_code}"
    html = fetch(url)
    if not html:
        return None

    # Extract the main content area
    # Look for the statute content — it's in <li><p> elements after the nav
    # Find the content block between header and footer
    content_match = re.search(
        r'<ul[^>]*class="[^"]*list-unstyled[^"]*"[^>]*>(.*?)</ul>\s*(?:<br|</div)',
        html, re.DOTALL | re.I
    )

    if content_match:
        content_html = content_match.group(1)
    else:
        # Fallback: extract everything between first § and end of content
        start = html.find('§')
        if start < 0:
            return None
        # Find a reasonable end
        end_markers = ['<footer', '</main>', '<!-- footer']
        end = len(html)
        for marker in end_markers:
            pos = html.find(marker, start)
            if pos > 0:
                end = min(end, pos)
        content_html = html[start:end]

    text = strip_html(content_html)

    # Clean up navigation artifacts
    text = re.sub(r'Skip to (navigation|subnav|content)\s*', '', text)
    text = re.sub(r'Toggle navigation\s*', '', text)
    text = re.sub(r'Searching \d{4}.*?session\s*', '', text)
    text = re.sub(r'Return to current session\s*', '', text)
    text = re.sub(r'Vermont\s+General\s+Assembly\s*', '', text)

    return text if len(text) > 50 else None


def parse_sections(text: str) -> List[Dict[str, str]]:
    """Parse individual sections from chapter text."""
    sections = []
    # Split on section markers: § NNN. Title
    parts = re.split(r'(§\s*\d+[a-z]*\.\s*[^\n]+)', text)

    current_section = None
    current_text = []

    for part in parts:
        sec_match = re.match(r'§\s*(\d+[a-z]*)\.\s*(.+)', part.strip())
        if sec_match:
            if current_section:
                sections.append({
                    "number": current_section["number"],
                    "title": current_section["title"],
                    "text": "\n".join(current_text).strip(),
                })
            current_section = {
                "number": sec_match.group(1),
                "title": sec_match.group(2).strip(),
            }
            current_text = []
        elif current_section:
            if part.strip():
                current_text.append(part.strip())

    if current_section:
        sections.append({
            "number": current_section["number"],
            "title": current_section["title"],
            "text": "\n".join(current_text).strip(),
        })

    return sections


def normalize(chapter_info: Dict, text: str) -> Dict:
    """Normalize a chapter record."""
    title_code = chapter_info["title_code"]
    chapter_code = chapter_info["chapter_code"]
    chapter_name = chapter_info.get("chapter_name", "")
    title_name = chapter_info.get("title_name", "")

    doc_title = f"Title {title_code}, Chapter {chapter_code}"
    if chapter_name:
        doc_title += f": {chapter_name}"

    return {
        "_id": f"VT-T{title_code}-C{chapter_code}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": doc_title,
        "text": text,
        "date": None,
        "url": f"{BASE_URL}/statutes/fullchapter/{title_code}/{chapter_code}",
        "jurisdiction": "US-VT",
        "title_number": title_code,
        "title_name": title_name,
        "chapter_number": chapter_code,
        "chapter_name": chapter_name,
    }


def fetch_all(limit: Optional[int] = None) -> Iterator[Dict]:
    """Fetch all chapters from all titles."""
    count = 0
    titles = discover_titles()

    for title_code in titles:
        if limit and count >= limit:
            return

        chapters = discover_chapters(title_code)
        logger.info(f"Title {title_code}: {len(chapters)} chapters")
        time.sleep(CRAWL_DELAY)

        for ch in chapters:
            if limit and count >= limit:
                return

            text = fetch_chapter_text(ch["title_code"], ch["chapter_code"])
            time.sleep(CRAWL_DELAY)

            if not text or len(text) < 100:
                logger.warning(
                    f"Skipping Title {ch['title_code']} Ch {ch['chapter_code']}: "
                    f"insufficient text ({len(text) if text else 0} chars)"
                )
                continue

            record = normalize(ch, text)
            yield record
            count += 1
            logger.info(f"[{count}] {record['title'][:80]} ({len(text)} chars)")

    logger.info(f"Total chapters fetched: {count}")


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
