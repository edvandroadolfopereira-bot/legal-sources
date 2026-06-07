#!/usr/bin/env python3
"""
FJ/FCCC-Decisions -- Fijian Competition & Consumer Commission

Fetches media releases, price control orders, LPG authorisations,
enforcement decisions and regulatory determinations via the WordPress
REST API at fccc.gov.fj.

Most posts link to PDF attachments; text is extracted via common/pdf_extract.
Posts without PDFs use inline HTML content (stripped of tags).

Strategy:
  1. Paginate wp-json/wp/v2/posts (100 per page, ~533 total)
  2. For each post, extract PDF URLs from content.rendered
  3. Download each PDF and extract text
  4. If no PDFs, use cleaned inline HTML text

Usage:
  python bootstrap.py bootstrap          # Full pull (~533 posts)
  python bootstrap.py bootstrap --sample # Fetch ~15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Same as bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import re
import json
import logging
import time
import html as html_mod
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.FJ.FCCC-Decisions")

USER_AGENT = (
    "LegalDataHunter/1.0 (open-data research; "
    "https://github.com/worldwidelaw/legal-sources)"
)
API_BASE = "https://fccc.gov.fj/wp-json/wp/v2"
REQUEST_DELAY = 1.5
PER_PAGE = 100

TAG_RE = re.compile(r"<[^>]+>")
PDF_LINK_RE = re.compile(
    r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE
)


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    text = TAG_RE.sub(" ", text)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _http_get(url: str, timeout: int = 30, accept: str = "*/*") -> Optional[bytes]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        resp = urlopen(req, timeout=timeout)
        return resp.read()
    except (HTTPError, URLError) as e:
        logger.warning(f"HTTP error for {url}: {e}")
        return None


def _http_get_json(url: str, timeout: int = 30):
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        resp = urlopen(req, timeout=timeout)
        import json as _json
        return _json.loads(resp.read())
    except (HTTPError, URLError) as e:
        logger.warning(f"API error for {url}: {e}")
        return None


def _download_pdf(url: str, timeout: int = 60) -> Optional[bytes]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=timeout)
        data = resp.read()
        if data and b"%PDF" in data[:20]:
            return data
    except (HTTPError, URLError) as e:
        logger.debug(f"PDF download failed for {url}: {e}")
    return None


def _extract_pdf_urls(html_content: str) -> List[str]:
    """Extract all PDF URLs from HTML content."""
    urls = []
    seen = set()
    for match in PDF_LINK_RE.finditer(html_content):
        url = match.group(1).strip()
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


class FCCCDecisionsScraper(BaseScraper):
    """
    Scraper for FJ/FCCC-Decisions.
    Country: FJ
    URL: https://fccc.gov.fj

    Data types: doctrine
    Auth: none (Open Data)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

    def _fetch_posts(self, max_records: int = 999999) -> Generator[dict, None, None]:
        """Paginate the WP REST API and yield raw post dicts with text."""
        count = 0
        page = 1

        while count < max_records:
            url = (
                f"{API_BASE}/posts?per_page={PER_PAGE}&page={page}"
                f"&_fields=id,date,title,content,link,categories"
            )
            logger.info(f"Fetching page {page}: {url}")
            time.sleep(REQUEST_DELAY)

            posts = _http_get_json(url)
            if not posts or not isinstance(posts, list) or len(posts) == 0:
                logger.info(f"No more posts at page {page}")
                break

            for post in posts:
                if count >= max_records:
                    return

                post_id = post.get("id", 0)
                title_raw = post.get("title", {}).get("rendered", "")
                title = _clean_html(title_raw)
                content_html = post.get("content", {}).get("rendered", "")
                post_date = post.get("date", "")
                post_link = post.get("link", "")

                # Extract PDF URLs
                pdf_urls = _extract_pdf_urls(content_html)

                # Try to get text from PDFs
                texts = []
                for pdf_url in pdf_urls:
                    if count >= max_records:
                        break
                    time.sleep(REQUEST_DELAY)
                    pdf_bytes = _download_pdf(pdf_url)
                    if not pdf_bytes:
                        logger.debug(f"  PDF failed: {pdf_url}")
                        continue

                    fname = pdf_url.rsplit("/", 1)[-1]
                    pdf_id = re.sub(r"\.pdf$", "", fname, flags=re.IGNORECASE)
                    pdf_id = re.sub(r"[^a-zA-Z0-9_-]", "_", pdf_id)[:120]

                    pdf_text = extract_pdf_markdown(
                        source="FJ/FCCC-Decisions",
                        source_id=f"post-{post_id}-{pdf_id}",
                        pdf_bytes=pdf_bytes,
                        table="doctrine",
                    ) or ""

                    if pdf_text and len(pdf_text) >= 50:
                        texts.append(pdf_text)

                # Combine PDF texts or fall back to inline HTML
                if texts:
                    full_text = "\n\n---\n\n".join(texts)
                else:
                    inline_text = _clean_html(content_html)
                    if len(inline_text) >= 100:
                        full_text = inline_text
                    else:
                        logger.warning(
                            f"  Skipping post {post_id} ({title[:50]}): "
                            f"no PDFs extracted and inline text too short ({len(inline_text)} chars)"
                        )
                        continue

                yield {
                    "post_id": post_id,
                    "title": title,
                    "text": full_text,
                    "date": post_date,
                    "url": post_link,
                    "pdf_urls": pdf_urls,
                }
                count += 1
                logger.info(f"  [{count}] post {post_id}: {title[:60]} ({len(full_text)} chars)")

            page += 1

    def fetch_all(self) -> Generator[dict, None, None]:
        yield from self._fetch_posts()

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        yield from self._fetch_posts()

    def normalize(self, raw: dict) -> dict:
        post_id = raw.get("post_id", 0)
        date_str = raw.get("date", "")
        if date_str and "T" in date_str:
            date_str = date_str[:10]  # YYYY-MM-DD

        return {
            "_id": f"post-{post_id}",
            "_source": "FJ/FCCC-Decisions",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw["text"],
            "date": date_str or None,
            "url": raw.get("url", ""),
            "post_id": post_id,
        }


if __name__ == "__main__":
    scraper = FCCCDecisionsScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        data = _http_get(f"{API_BASE}/posts?per_page=1")
        if data:
            print("OK: WP REST API reachable")
        else:
            print("FAIL: Cannot reach WP REST API")
            sys.exit(1)

    elif command in ("bootstrap", "bootstrap-fast", "update"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        limit = 15 if sample else 999999

        if sample:
            logger.info("=== SAMPLE MODE: fetching ~15 records ===")

        for raw in scraper._fetch_posts(max_records=limit):
            record = scraper.normalize(raw)
            out_file = sample_dir / f"{record['_id']}.json"
            out_file.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            count += 1
            logger.info(f"Saved [{count}]: {record['title'][:70]}")

        logger.info(f"Done. Total records: {count}")
        if count == 0:
            logger.error("No records fetched — check connectivity")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
