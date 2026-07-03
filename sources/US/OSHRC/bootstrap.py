#!/usr/bin/env python3
"""
US/OSHRC -- Occupational Safety & Health Review Commission Decisions

Fetches OSHRC decisions via the WordPress REST API + media attachments.
~8,300+ decisions (Commission + ALJ) with full text from HTML attachments.

Data access:
  - WP REST API: /wp-json/wp/v2/decisions?per_page=100&page=N
  - Media attachments: /wp-json/wp/v2/media?parent={id}
  - HTML attachments contain full decision text (preferred over PDF)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Incremental (newest first)
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from html.parser import HTMLParser

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.OSHRC")

BASE_URL = "https://www.oshrc.gov"
API_URL = BASE_URL + "/wp-json/wp/v2"
DECISIONS_URL = API_URL + "/decisions"
MEDIA_URL = API_URL + "/media"
DELAY = 1.5
PER_PAGE = 100

# Decision category IDs
CAT_ALJ = 28        # Final ALJ Decisions
CAT_COMMISSION = 29  # Final Commission Decisions

CAT_NAMES = {
    CAT_ALJ: "ALJ Decision",
    CAT_COMMISSION: "Commission Decision",
}


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, stripping all tags."""

    def __init__(self):
        super().__init__()
        self._pieces: List[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip = True
        elif tag in ("br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                      "li", "tr", "blockquote"):
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = False
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                      "li", "tr", "blockquote"):
            self._pieces.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._pieces.append(data)

    def get_text(self) -> str:
        raw = "".join(self._pieces)
        # Collapse whitespace but keep paragraph breaks
        lines = raw.split("\n")
        cleaned = []
        for line in lines:
            line = " ".join(line.split())
            cleaned.append(line)
        text = "\n".join(cleaned)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def strip_html(html: str) -> str:
    """Strip HTML tags and return clean text."""
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html)
        return extractor.get_text()
    except Exception:
        # Fallback: regex strip
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&#\d+;", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    })
    return session


class OSHRCScraper:
    SOURCE_ID = "US/OSHRC"

    def __init__(self):
        self.session = get_session()

    def _get_json(self, url: str, params: dict = None) -> Optional[Any]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 400:
                    # WP returns 400 for pages beyond total
                    return None
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning("Rate limited, waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                logger.warning("HTTP %d for %s", resp.status_code, url)
                return None
            except requests.RequestException as e:
                logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                time.sleep(5)
        return None

    def _get_text(self, url: str) -> Optional[str]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 200:
                    return resp.text
                logger.warning("HTTP %d fetching %s", resp.status_code, url)
                return None
            except requests.RequestException as e:
                logger.warning("Fetch error (attempt %d): %s", attempt + 1, e)
                time.sleep(5)
        return None

    def fetch_decisions_page(self, page: int) -> List[Dict]:
        """Fetch one page of decisions from the WP REST API."""
        data = self._get_json(DECISIONS_URL, params={
            "per_page": PER_PAGE,
            "page": page,
            "orderby": "date",
            "order": "desc",
        })
        if data is None or not isinstance(data, list):
            return []
        return data

    def fetch_media(self, decision_id: int) -> List[Dict]:
        """Fetch media attachments for a decision."""
        data = self._get_json(MEDIA_URL, params={
            "parent": decision_id,
            "per_page": 20,
        })
        if data is None or not isinstance(data, list):
            return []
        return data

    def extract_full_text(self, media_items: List[Dict]) -> str:
        """Download and extract text from the best available attachment."""
        # Prefer HTML over PDF
        html_url = None
        pdf_url = None
        for item in media_items:
            mime = item.get("mime_type", "")
            source_url = item.get("source_url", "")
            if mime == "text/html" or source_url.endswith(".html") or source_url.endswith(".htm"):
                html_url = source_url
            elif mime == "application/pdf" or source_url.endswith(".pdf"):
                pdf_url = source_url

        if html_url:
            html_content = self._get_text(html_url)
            if html_content:
                text = strip_html(html_content)
                if len(text) > 100:
                    return text

        # PDF fallback - just record the URL, we can't extract inline
        if pdf_url and not html_url:
            logger.info("Only PDF available: %s", pdf_url)
            return ""

        return ""

    def extract_docket_number(self, title: str, text: str) -> str:
        """Try to extract docket number from the decision text or title."""
        # Common patterns: "OSHRC Docket No. XX-XXXX" or "Docket No(s). XX-XXXX"
        patterns = [
            r"(?:OSHRC\s+)?[Dd]ocket\s+No\.?\s*(?:\(s\)\.?)?\s*([\d]+-[\d]+(?:\s*(?:&|,)\s*[\d]+-[\d]+)*)",
            r"DOCKET\s+(?:NO\.?\s*)?([\d]+-[\d]+(?:\s*(?:&|,)\s*[\d]+-[\d]+)*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:3000])
            if match:
                return match.group(1).strip()
        # Also try title for embedded docket references
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                return match.group(1).strip()
        return ""

    def normalize(self, decision: Dict, media: List[Dict], full_text: str) -> Dict[str, Any]:
        """Normalize a decision into the standard schema."""
        wp_id = decision.get("id", 0)
        title = decision.get("title", {}).get("rendered", "").strip()
        date_str = decision.get("date", "")[:10]  # YYYY-MM-DD
        link = decision.get("link", "")
        slug = decision.get("slug", "")
        categories = decision.get("decision-categories", [])

        # Determine decision type
        decision_type = "Unknown"
        for cat_id in categories:
            if cat_id in CAT_NAMES:
                decision_type = CAT_NAMES[cat_id]

        # Get docket number
        docket = self.extract_docket_number(title, full_text)

        # Get attachment URLs
        attachment_urls = []
        for item in media:
            source_url = item.get("source_url", "")
            if source_url:
                attachment_urls.append(source_url)

        # Use slug + wp_id as stable ID
        record_id = f"oshrc-{wp_id}"

        return {
            "_id": record_id,
            "_source": "US/OSHRC",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "date": date_str if date_str else None,
            "url": link,
            "text": full_text,
            "docket_number": docket,
            "decision_type": decision_type,
            "wp_id": wp_id,
            "slug": slug,
            "attachment_urls": attachment_urls,
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict, None, None]:
        """Fetch all decisions."""
        page = 1
        total_yielded = 0
        max_records = 15 if sample else 999999

        while total_yielded < max_records:
            logger.info("Fetching decisions page %d...", page)
            decisions = self.fetch_decisions_page(page)
            if not decisions:
                logger.info("No more decisions at page %d", page)
                break

            for decision in decisions:
                if total_yielded >= max_records:
                    break

                wp_id = decision.get("id", 0)
                title = decision.get("title", {}).get("rendered", "")
                logger.info("Processing [%d] %s", wp_id, title[:60])

                # Fetch media attachments
                time.sleep(DELAY)
                media = self.fetch_media(wp_id)

                # Extract full text
                full_text = ""
                if media:
                    time.sleep(DELAY)
                    full_text = self.extract_full_text(media)

                if not full_text:
                    # Try content field as fallback
                    content = decision.get("content", {}).get("rendered", "")
                    if content:
                        full_text = strip_html(content)

                if not full_text:
                    logger.warning("No text for decision %d: %s", wp_id, title[:60])
                    continue

                record = self.normalize(decision, media, full_text)
                total_yielded += 1
                yield record

            page += 1
            time.sleep(DELAY)

        logger.info("Total decisions yielded: %d", total_yielded)

    def test(self) -> bool:
        """Quick connectivity test."""
        data = self._get_json(DECISIONS_URL, params={"per_page": 1})
        if data and isinstance(data, list) and len(data) > 0:
            title = data[0].get("title", {}).get("rendered", "")
            logger.info("Connection OK. First decision: %s", title)
            return True
        logger.error("Connection test failed")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="US/OSHRC bootstrap")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample records only")
    parser.add_argument("--full", action="store_true", help="Alias for no-sample")
    args = parser.parse_args()

    scraper = OSHRCScraper()

    if args.command == "test":
        success = scraper.test()
        sys.exit(0 if success else 1)

    sample_mode = args.sample and not args.full
    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        for record in scraper.fetch_all(sample=sample_mode):
            out_path = sample_dir / f"{record['_id']}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
            text_len = len(record.get("text", ""))
            logger.info("Saved %s (%d chars)", out_path.name, text_len)

        logger.info("Bootstrap complete: %d records saved", count)

    elif args.command == "update":
        # Incremental: fetch newest page only
        for record in scraper.fetch_all(sample=True):
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
