#!/usr/bin/env python3
"""
INTL/CIMA-Code -- CIMA Insurance Code Fetcher (Code des Assurances)

Fetches the full text of the CIMA Insurance Code (Code des Assurances des
Etats membres de la CIMA), the directly-applicable regional insurance law of
14 francophone African states, from cima-afrique.org.

The code is published as a HelpNDoc HTML export under
/wp-content/code-cima/fr/. Each article / section is its own HTML page, and
the pages cross-link to one another. The scraper performs a breadth-first
crawl from the root page, following every local .html link within the code
directory, and extracts the visible body text of each topic page.

Strategy:
  - BFS crawl from AVANTPROPOS.html within /wp-content/code-cima/fr/
  - For each discovered page, extract visible text (strip nav/scripts)
  - Keep pages with a meaningful amount of legislative text
  - Respect a polite crawl delay

Usage:
  python bootstrap.py bootstrap          # Fetch all topic pages
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
import html as html_lib
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from typing import Generator, Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.CIMA-Code")

BASE_DIR = "https://cima-afrique.org/wp-content/code-cima/fr/"
START_PAGE = "AVANTPROPOS.html"
LANDING_URL = "https://cima-afrique.org/code-cima/"

# Page filename -> local .html links (topic pages live in the same directory)
LINK_RE = re.compile(r'href="([A-Za-z0-9_]+\.html)"')

MIN_TEXT_CHARS = 300       # skip pure-navigation / stub pages
MAX_PAGES = 2000           # safety cap


class CimaCodeScraper(BaseScraper):
    """Scraper for INTL/CIMA-Code -- the CIMA Insurance Code."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.5,en;q=0.3",
        })

    def _request(self, url: str, timeout: int = 45) -> Optional[requests.Response]:
        """HTTP GET with polite delay and retry."""
        for attempt in range(3):
            try:
                time.sleep(0.5)
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 20s")
                    time.sleep(20)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(5)
        return None

    def _extract(self, html: str) -> Dict[str, str]:
        """Extract title and visible body text from a topic page."""
        soup = BeautifulSoup(html, "html.parser")

        # Drop chrome that is not part of the legal text
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Title: prefer the topic heading, fall back to <title>
        title = ""
        for sel in ["h1", "h2", "title"]:
            el = soup.find(sel)
            if el:
                t = el.get_text(strip=True)
                # The HelpNDoc <title> repeats the code name; keep the heading
                if t and t.lower() not in ("code cima 2019",):
                    title = t
                    break

        # Body: the main content container if present, else the whole body
        container = soup.find(id="main") or soup.find("body") or soup
        text = container.get_text(separator="\n", strip=True)
        text = html_lib.unescape(text)

        # Remove the HelpNDoc boilerplate lines
        drop = (
            "Skip to main content", "Toggle navigation", "CODE CIMA 2019",
            "Contents", "Index", "Rechercher", "Close",
            "Créé avec", "Éditeur de documentation",
        )
        lines = []
        for ln in text.split("\n"):
            s = ln.strip()
            if not s:
                continue
            if any(s.startswith(d) or s == d for d in drop):
                continue
            lines.append(s)
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        return {"title": title, "text": text}

    def _make_doc_id(self, filename: str) -> str:
        stem = filename[:-5] if filename.endswith(".html") else filename
        return f"cima-code-{stem}"

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": self._make_doc_id(raw["filename"]),
            "_source": "INTL/CIMA-Code",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
        }

    def _crawl(self, max_records: int = None) -> Generator[Dict[str, Any], None, None]:
        """BFS crawl over the code directory, yielding normalized records."""
        seen = set()
        queue = deque([START_PAGE])
        emitted = 0

        while queue and len(seen) < MAX_PAGES:
            filename = queue.popleft()
            if filename in seen:
                continue
            seen.add(filename)

            resp = self._request(BASE_DIR + filename)
            if resp is None:
                continue

            html = resp.text

            # Enqueue newly discovered local topic pages
            for link in LINK_RE.findall(html):
                if link not in seen and link not in queue:
                    queue.append(link)

            extracted = self._extract(html)
            if len(extracted["text"]) < MIN_TEXT_CHARS:
                continue

            raw = {
                "filename": filename,
                "title": extracted["title"] or filename[:-5],
                "text": extracted["text"],
                "url": BASE_DIR + filename,
                "date": "",
            }
            yield self.normalize(raw)
            emitted += 1
            if max_records and emitted >= max_records:
                return

        logger.info(f"Crawl complete: visited {len(seen)} pages, emitted {emitted}")

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        yield from self._crawl()

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        # The code is a consolidated text; a full re-crawl is the update path.
        yield from self._crawl()

    def test(self) -> bool:
        resp = self._request(BASE_DIR + START_PAGE)
        if resp is None:
            logger.error("Cannot reach CIMA code root page")
            return False
        links = LINK_RE.findall(resp.text)
        logger.info(f"Root page OK: {len(set(links))} local links")
        # Pull one content page
        for f in ["Article1.html", "REGLEMENTSDUCONSEILDESMINISTRESD.html"]:
            r = self._request(BASE_DIR + f)
            if r:
                ex = self._extract(r.text)
                logger.info(f"{f}: {len(ex['text'])} chars -- {ex['title'][:60]}")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="INTL/CIMA-Code data fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch a small sample")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = CimaCodeScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)

    if args.command == "update":
        count = 0
        for _ in scraper.fetch_updates():
            count += 1
        logger.info(f"Update complete: {count} records")
        return

    # bootstrap / bootstrap-fast
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    max_records = 15 if args.sample else None
    jsonl_path = data_dir / "records.jsonl"
    count = 0
    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for record in scraper.fetch_all():
            if args.sample and count < 15:
                out = sample_dir / f"record_{count:04d}.json"
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
            elif not args.sample:
                if count < 15:
                    out = sample_dir / f"record_{count:04d}.json"
                    with open(out, "w", encoding="utf-8") as f:
                        json.dump(record, f, ensure_ascii=False, indent=2)
                jf.write(json.dumps(record, ensure_ascii=False) + "\n")
            text_len = len(record.get("text", ""))
            logger.info(f"[{count+1}] {record.get('title','?')[:70]} ({text_len:,} chars)")
            count += 1
            if max_records and count >= max_records:
                break

    logger.info(f"Bootstrap complete: {count} records")


if __name__ == "__main__":
    main()
