#!/usr/bin/env python3
"""
AF/AsianLII -- Afghanistan Laws (English translations) via the Wayback Machine.

AsianLII (asianlii.org/af/legis/laws/) hosts English translations of
Afghanistan's principal legislation -- the Civil Code, Penal Code, Commercial
Code, Constitution, Labour Law, and dozens of other acts -- as AustLII-style
static HTML pages with the full statute text inline.

The live site is now behind a Cloudflare JS challenge (HTTP 403 to every
non-browser client), so this scraper retrieves the same content from the
Internet Archive Wayback Machine, which is not Cloudflare-gated:

  1. The CDX API enumerates every archived document page under
     /af/legis/laws/<slug>/ that returned HTTP 200.
  2. Each document is fetched as a raw ("id_") Wayback snapshot, preserving the
     original AsianLII HTML untouched by the Wayback toolbar.
  3. Full text is extracted from the HTML: the title from <TITLE>, and the body
     between the first <HR> rule and the AsianLII copyright footer.

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py test
"""

import argparse
import html as ihtml
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AF.AsianLII")

SOURCE_ID = "AF/AsianLII"
DELAY = 1.0

CDX_API = "https://web.archive.org/cdx/search/cdx"
WB_RAW = "https://web.archive.org/web/{ts}id_/{url}"

# Canonical AsianLII Afghan-law document page: /af/legis/laws/<slug>/ where the
# slug has no dot (excludes the .txt / .pdf / .rtf download variants).
DOC_RE = re.compile(r"/af/legis/laws/([a-z0-9]+)/?$", re.IGNORECASE)

UA = {"User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0; +legal-data-hunter)"}


def _get(url: str, *, as_json: bool = False, retries: int = 3):
    """HTTP GET with retries. Returns text, parsed JSON, or None."""
    for attempt in range(retries):
        try:
            time.sleep(DELAY)
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            logger.warning("GET %s -> HTTP %d (attempt %d)", url, r.status_code, attempt + 1)
        except Exception as e:
            logger.warning("GET %s failed: %s (attempt %d)", url, e, attempt + 1)
        if attempt < retries - 1:
            time.sleep(3)
    return None


def _enumerate_docs() -> List[Tuple[str, str, str]]:
    """Query the Wayback CDX API for every archived Afghan-law document page.

    Returns a list of (slug, original_url, timestamp) tuples, one per distinct
    law, choosing the most recent HTTP-200 capture for each.
    """
    params = (
        "?url=asianlii.org/af/legis/laws/*"
        "&output=json&fl=original,timestamp&filter=statuscode:200&limit=50000"
    )
    data = _get(CDX_API + params, as_json=True)
    if not data or len(data) < 2:
        return []
    rows = data[1:]  # drop header row
    best: Dict[str, Tuple[str, str]] = {}
    for orig, ts in rows:
        m = DOC_RE.search(orig)
        if not m:
            continue
        slug = m.group(1).lower()
        # Keep the most recent capture per slug.
        if slug not in best or ts > best[slug][1]:
            best[slug] = (orig, ts)
    docs = [(slug, orig, ts) for slug, (orig, ts) in best.items()]
    docs.sort(key=lambda d: d[0])
    return docs


_DATE_RE = re.compile(r"published\s+(\d{4})/(\d{1,2})/(\d{1,2})", re.IGNORECASE)
_GAZ_RE = re.compile(r"Official Gazette\s+No\.?\s*(\d+)", re.IGNORECASE)


def _extract(html: str) -> Tuple[str, str]:
    """Extract (title, full_text) from an AsianLII document HTML page."""
    tm = re.search(r"<TITLE>(.*?)</TITLE>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", ihtml.unescape(tm.group(1))).strip() if tm else ""

    # Body sits between the first <HR> (after the nav/breadcrumb block) and the
    # AsianLII copyright footer.
    hr = re.search(r"<HR[^>]*>", html, re.I)
    start = hr.end() if hr else 0
    foot = re.search(r"AsianLII:\s*(?:<[^>]+>\s*)*Copyright Policy", html, re.I)
    if not foot:
        foot = re.search(r"Copyright Policy\s*\|", html, re.I)
    end = foot.start() if foot else len(html)
    body = html[start:end]

    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", body)
    body = re.sub(r"(?is)<HR[^>]*>\s*$", "", body)
    txt = re.sub(r"<[^>]+>", " ", body)
    txt = ihtml.unescape(txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = "\n".join(line.strip() for line in txt.splitlines())
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return title, txt


def _parse_date(title: str) -> Optional[str]:
    m = _DATE_RE.search(title)
    if not m:
        return None
    y, mo, d = m.groups()
    try:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    except ValueError:
        return None


class AsianLIIScraper(BaseScraper):
    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        docs = _enumerate_docs()
        logger.info("Enumerated %d Afghan-law document pages from Wayback CDX", len(docs))
        count = 0
        for slug, orig, ts in docs:
            url = WB_RAW.format(ts=ts, url=orig)
            html = _get(url)
            if not html:
                logger.warning("No snapshot for %s", slug)
                continue
            title, text = _extract(html)
            if not text or len(text) < 500:
                logger.warning("Insufficient text (%d chars): %s", len(text or ""), slug)
                continue
            if "available only in pdf" in text.lower():
                # AsianLII has only a scanned-PDF placeholder for this act, no
                # HTML body — same scanned-PDF/OCR gap as AF/MOJLaws. Skip it.
                logger.info("PDF-only placeholder, skipping: %s", slug)
                continue
            count += 1
            logger.info("[%d] %s (%d chars)", count, title[:70], len(text))
            yield {
                "slug": slug,
                "title": title,
                "text": text,
                "date": _parse_date(title),
                "gazette": (_GAZ_RE.search(title).group(1) if _GAZ_RE.search(title) else None),
                # Canonical live URL (without the Wayback wrapper).
                "url": orig.replace("http://", "https://"),
                "wayback_url": url,
            }
        logger.info("Completed: %d documents fetched", count)

    def fetch_updates(self, since=None) -> Generator[Dict[str, Any], None, None]:
        # Static historical corpus — updates re-scan the full set (upsert dedup).
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": f"AF_AsianLII_{raw['slug']}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "gazette_number": raw.get("gazette"),
            "url": raw.get("url", ""),
            "wayback_url": raw.get("wayback_url", ""),
            "jurisdiction": "AF",
            "language": "en",
        }

    def test(self) -> bool:
        docs = _enumerate_docs()
        logger.info("CDX enumeration: %d Afghan-law pages", len(docs))
        if not docs:
            logger.error("No documents enumerated")
            return False
        slug, orig, ts = docs[0]
        html = _get(WB_RAW.format(ts=ts, url=orig))
        if not html:
            logger.error("Snapshot fetch failed for %s", slug)
            return False
        title, text = _extract(html)
        logger.info("First doc: %s | %d chars", title[:70], len(text))
        return len(text) >= 200


def main():
    parser = argparse.ArgumentParser(description="AF/AsianLII data fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = AsianLIIScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.bootstrap(sample_mode=args.sample, sample_size=15)
    elif args.command == "update":
        scraper.bootstrap(sample_mode=False)


if __name__ == "__main__":
    main()
