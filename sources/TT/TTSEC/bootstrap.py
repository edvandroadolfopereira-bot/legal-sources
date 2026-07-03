#!/usr/bin/env python3
"""
TT/TTSEC -- Trinidad & Tobago Securities Exchange Commission

Fetches enforcement orders, regulatory notices, guidelines, circulars,
bye-laws, and investor alerts from the TTSEC website with full text.

Strategy (2026-06 rewrite):
  The WordPress REST API (/wp-json/wp/v2/posts) is now restricted by the
  site's "Kadence Security" settings — it returns HTTP 401
  (itsec_rest_api_access_restricted) for all clients. We therefore
  enumerate posts from the public XML sitemaps instead:

  - Collect every post permalink from /post-sitemap*.xml (paginated, 1000/file)
  - Keep only regulatory documents (slug keyword filter — orders, notices,
    guidelines, bye-laws, rules, circulars, hearings, contraventions, etc.)
  - Fetch each post's HTML page
  - Extract the attached PDF (/wp-content/uploads/*.pdf) and pull full text
    via common/pdf_extract; fall back to the post's HTML body text
  - Title from og:title, date from the JSON-LD datePublished / og meta

The public HTML site and sitemaps remain fully accessible; only the JSON
REST API is gated.

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch 15 sample records
  python bootstrap.py bootstrap-fast --full
  python bootstrap.py test                 # Quick connectivity test
"""

import sys
import re
import logging
import json
import time
import html as html_mod
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.TT.TTSEC")

BASE_URL = "https://www.ttsec.org.tt"
SITEMAP_INDEX = f"{BASE_URL}/wp-sitemap.xml"

# Slug keywords that identify a regulatory/legal document (vs. news, team
# bios, events, etc.). Matched case-insensitively against the post permalink.
DOC_KEYWORDS = [
    "order", "exemption", "by-law", "bye-law", "byelaw", "notice",
    "guideline", "circular", "rule", "decision", "hearing", "contravention",
    "settlement", "de-list", "delist", "deregistration", "directive",
    "market-guidance", "take-over", "takeover", "moratorium", "policy",
    "framework", "amendment", "registration", "prospectus", "securities-",
    "sanction", "fine", "advisory", "alert",
]


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class TTSECScraper(BaseScraper):
    """Scraper for TT/TTSEC -- Trinidad & Tobago Securities Exchange Commission."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_request = 0.0

    def _get(self, url: str) -> Optional[str]:
        """Rate-limited GET returning response text, with retry."""
        elapsed = time.time() - self._last_request
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request = time.time()
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(5)
        return None

    # ── Sitemap enumeration ──────────────────────────────────────────

    def _post_sitemaps(self) -> List[str]:
        """Return the list of post-sitemap*.xml URLs from the sitemap index."""
        text = self._get(SITEMAP_INDEX)
        if not text:
            return []
        sitemaps = re.findall(r"<loc>([^<]+post-sitemap[^<]*\.xml)</loc>", text)
        return sitemaps

    def _iter_post_urls(self) -> Generator[str, None, None]:
        """Yield every regulatory post permalink from the post sitemaps."""
        seen = set()
        for sm in self._post_sitemaps():
            text = self._get(sm)
            if not text:
                continue
            for url in re.findall(r"<loc>([^<]+)</loc>", text):
                low = url.lower()
                if not any(kw in low for kw in DOC_KEYWORDS):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                yield url

    # ── Post page parsing ────────────────────────────────────────────

    def _parse_post(self, url: str) -> Optional[dict]:
        """Fetch a post page and extract title, date, PDF URL, and body."""
        html_text = self._get(url)
        if not html_text:
            return None

        # Title from og:title (strip the trailing " - TTSEC | ..." site suffix)
        title = ""
        m = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
                      html_text)
        if m:
            title = html_mod.unescape(m.group(1))
        else:
            m = re.search(r"<title>(.*?)</title>", html_text, re.S)
            if m:
                title = html_mod.unescape(m.group(1).strip())
        title = re.split(r"\s+-\s+TTSEC\b", title)[0].strip()

        # Publication date (ISO) from JSON-LD or og meta
        date = None
        m = (re.search(r'"datePublished"\s*:\s*"([^"]+)"', html_text)
             or re.search(r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
                          html_text))
        if m:
            date = m.group(1)

        # PDF attachment (uploads dir), preferring an English/non-thumbnail file
        pdf_urls = re.findall(r'href=["\']([^"\']+/wp-content/uploads/[^"\']+\.pdf)["\']',
                              html_text, re.I)
        if not pdf_urls:
            pdf_urls = re.findall(r'href=["\']([^"\']+\.pdf)["\']', html_text, re.I)
        pdf_url = None
        if pdf_urls:
            pdf_url = pdf_urls[0]
            if not pdf_url.startswith("http"):
                pdf_url = BASE_URL + (pdf_url if pdf_url.startswith("/") else "/" + pdf_url)

        # HTML body fallback (entry content area, cut at footer/comments)
        body = ""
        cm = re.search(r'class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)</article>',
                       html_text, re.S)
        if not cm:
            cm = re.search(r'class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>(.*?)<footer',
                           html_text, re.S)
        if cm:
            body = _strip_html(cm.group(1))[:200000]

        return {
            "url": url,
            "title": title,
            "date": date,
            "pdf_url": pdf_url,
            "html_body": body,
        }

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all regulatory documents with full text."""
        total = 0
        for url in self._iter_post_urls():
            post = self._parse_post(url)
            if not post:
                continue

            doc_id = url.rstrip("/").split("/")[-1]
            text = None

            if post.get("pdf_url"):
                try:
                    pdf_text = extract_pdf_markdown(
                        "TT/TTSEC", doc_id,
                        pdf_url=post["pdf_url"], table="doctrine", force=True,
                    )
                    if pdf_text and len(pdf_text.strip()) > 100:
                        text = pdf_text.strip()
                except Exception as e:
                    logger.warning(f"PDF extract failed for {post['pdf_url']}: {e}")

            if not text and post.get("html_body") and len(post["html_body"]) >= 200:
                text = post["html_body"]

            if not text:
                logger.debug(f"Skipping post with no full text: {url}")
                continue

            total += 1
            yield {
                "id": doc_id,
                "title": post["title"],
                "text": text,
                "date": post["date"],
                "url": post["pdf_url"] or url,
                "link": url,
            }

        logger.info(f"Total: {total} documents with full text")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield documents published since the given date (best-effort by date)."""
        for raw in self.fetch_all():
            ds = raw.get("date")
            if not ds:
                yield raw
                continue
            try:
                dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                if dt >= since:
                    yield raw
            except (ValueError, TypeError):
                yield raw

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        date_str = raw.get("date", "") or ""
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_str = ""

        return {
            "_id": raw.get("id", ""),
            "_source": "TT/TTSEC",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": date_str,
            "url": raw.get("url", ""),
            "link": raw.get("link", ""),
        }


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    scraper = TTSECScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample] [--full]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "test":
        logger.info("Testing TTSEC sitemap access...")
        sms = scraper._post_sitemaps()
        logger.info(f"Found {len(sms)} post sitemaps")
        n = 0
        for url in scraper._iter_post_urls():
            logger.info(f"  {url}")
            n += 1
            if n >= 5:
                break
        if n:
            post = scraper._parse_post(url)
            logger.info(f"sample post: title={post['title'][:50]!r} "
                        f"pdf={bool(post['pdf_url'])} date={post['date']}")
            print("Test passed: sitemap + post pages accessible")
        else:
            logger.error("No regulatory posts found")
            sys.exit(1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample = "--sample" in sys.argv
        result = scraper.bootstrap(sample_mode=sample, sample_size=15)
        print(json.dumps(result, indent=2, default=str))

    elif command == "update":
        from datetime import timedelta
        result = scraper.bootstrap(sample_mode=False)
        print(json.dumps(result, indent=2, default=str))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
