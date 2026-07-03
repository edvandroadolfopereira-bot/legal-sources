#!/usr/bin/env python3
"""
LA/LaoTradePortal -- Lao Trade Information Portal (Legal Documents)

Fetches trade-related legal documents from the Lao PDR Trade Information Portal,
maintained by the Ministry of Industry and Commerce. The portal hosts ~1000+
documents including laws, decrees, decisions, notifications, orders, regulations,
instructions, provisions, and edicts — all in English translation.

The listing page at /en-gb/legal-document/index contains an HTML DataTable with
all documents (no pagination/AJAX needed). Each row has:
  - Title (with link to /en-gb/site/display/{ID})
  - Type (Law, Decree, Decision, etc.)
  - Responsible Agency
  - Issuing Agency
  - Issue Date (YYYY-MM-DD)
  - Created On (YYYY-MM-DD)

Full text is extracted from individual document pages by stripping HTML from the
main content area.

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # Sample (15 docs)
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py update             # Re-fetch
  python bootstrap.py test               # Connectivity test
"""

import re
import sys
import json
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.LA.LaoTradePortal")

BASE_URL = "https://www.laotradeportal.gov.la"
LISTING_URL = f"{BASE_URL}/en-gb/legal-document/index"
DOC_URL_TEMPLATE = f"{BASE_URL}/en-gb/site/display/{{id}}"


class LaoTradePortalScraper(BaseScraper):
    """
    Scraper for LA/LaoTradePortal.
    Country: LA
    URL: https://www.laotradeportal.gov.la/en-gb/legal-document/index

    Data types: legislation
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (open-data research project)",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _parse_listing(self) -> list[dict]:
        """Parse the listing page and extract document metadata."""
        resp = self.session.get(LISTING_URL, timeout=60)
        resp.raise_for_status()
        html = resp.text

        # Find the datatable_search_legal table
        table_start = html.find('id="datatable_search_legal"')
        if table_start < 0:
            raise RuntimeError("Could not find datatable_search_legal table")

        table_end = html.find("</table>", table_start)
        table_html = html[table_start:table_end]

        # Find rows after </thead>
        thead_end = table_html.find("</thead>")
        if thead_end < 0:
            raise RuntimeError("Could not find </thead> in table")

        rows_html = table_html[thead_end + len("</thead>"):]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", rows_html, re.DOTALL)

        documents = []
        for row_html in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            if len(cells) < 6:
                continue

            # Cell 0: row number
            # Cell 1: title with link
            # Cell 2: type
            # Cell 3: responsible agency
            # Cell 4: issuing agency
            # Cell 5: issue date
            # Cell 6: created on (optional)

            title_cell = cells[1]
            link_match = re.search(r'href="([^"]*display/(\d+))"', title_cell)
            if not link_match:
                continue

            doc_url = link_match.group(1)
            doc_id = link_match.group(2)
            title = re.sub(r"<[^>]+>", "", title_cell).strip()
            doc_type = re.sub(r"<[^>]+>", "", cells[2]).strip()
            responsible_agency = re.sub(r"<[^>]+>", "", cells[3]).strip()
            issuing_agency = re.sub(r"<[^>]+>", "", cells[4]).strip()
            issue_date = re.sub(r"<[^>]+>", "", cells[5]).strip()
            created_on = re.sub(r"<[^>]+>", "", cells[6]).strip() if len(cells) > 6 else ""

            # Ensure URL is absolute
            if doc_url.startswith("/"):
                doc_url = BASE_URL + doc_url

            documents.append({
                "doc_id": doc_id,
                "title": title,
                "doc_type": doc_type,
                "responsible_agency": responsible_agency,
                "issuing_agency": issuing_agency,
                "issue_date": issue_date if re.match(r"\d{4}-\d{2}-\d{2}", issue_date) else None,
                "created_on": created_on if re.match(r"\d{4}-\d{2}-\d{2}", created_on) else None,
                "url": doc_url,
            })

        logger.info(f"Parsed {len(documents)} documents from listing page")
        return documents

    def _fetch_full_text(self, url: str) -> str:
        """Fetch full text from an individual document page.

        Returns empty string if page only has Lao text or no extractable content.
        """
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return ""

        html = resp.text

        # Check if page says English version is not available
        lower = html.lower()
        if "english version will be available soon" in lower or \
           "english content will be available soon" in lower:
            return ""

        # Find content: look for the anchor 'top' which marks start of law text
        # Case-insensitive search since some pages use "Top" vs "top"
        start = -1
        html_lower = html.lower()
        for marker in ['<a name="top">', "<a name='top'>", 'name="top"']:
            idx = html_lower.find(marker)
            if idx >= 0:
                start = idx
                break

        if start < 0:
            # Fallback: look for class="p-3" div which wraps the content
            idx = html.find('class="p-3"')
            if idx >= 0:
                start = idx

        if start < 0:
            # Fallback: look for the first heading after the breadcrumb
            for tag in ["<h4", "<h3", "<h2"]:
                idx = html.find(tag, len(html) // 4)
                if idx >= 0:
                    start = idx
                    break

        if start < 0:
            return ""

        # Find end boundary
        end_markers = [
            "Thanks for sharing",
            "Have you found this information useful",
            "btn-outline-primary",
            '<div class="modal',
            "feedback-form",
            "Your opinion matters",
        ]
        end = len(html)
        for marker in end_markers:
            idx = html.find(marker, start)
            if idx >= 0 and idx < end:
                end = idx

        text_area = html[start:end]

        # Strip HTML tags
        import html as html_mod
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text_area, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</?p[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"</?(?:div|section|article|header|footer)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"</?(?:h[1-6])[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"</?(?:li|ul|ol)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"</?tr[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"</?td[^>]*>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities
        text = html_mod.unescape(text)

        # Clean whitespace and artifacts
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        text = text.strip()

        # Remove leading div class attributes that leaked through
        text = re.sub(r'^class="[^"]*">\s*', "", text)

        # Skip if text is too short (likely just a PDF download stub)
        if len(text) < 200:
            return ""

        return text

    def normalize(self, raw: dict) -> dict:
        """Transform raw data into standard schema."""
        doc_id = raw["doc_id"]
        title = raw["title"]

        return {
            "_id": f"LA/LaoTradePortal/{doc_id}",
            "_source": "LA/LaoTradePortal",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": raw.get("issue_date"),
            "url": raw.get("url", ""),
            "doc_type": raw.get("doc_type", ""),
            "responsible_agency": raw.get("responsible_agency", ""),
            "issuing_agency": raw.get("issuing_agency", ""),
            "created_on": raw.get("created_on"),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Yield all documents with full text."""
        documents = self._parse_listing()

        if sample:
            # Pick a diverse sample: first 5, middle 5, last 5
            n = len(documents)
            indices = list(range(min(5, n)))
            indices += list(range(n // 2 - 2, min(n // 2 + 3, n)))
            indices += list(range(max(0, n - 5), n))
            indices = sorted(set(indices))
            documents = [documents[i] for i in indices if i < n]
            logger.info(f"Sample mode: selected {len(documents)} documents")

        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Fetching: {doc['title'][:80]}...")

            text = self._fetch_full_text(doc["url"])
            if not text:
                logger.warning(f"  No text extracted for doc {doc['doc_id']}")
                continue

            doc["text"] = text
            record = self.normalize(doc)

            if len(record.get("text", "")) < 100:
                logger.warning(f"  Very short text ({len(record['text'])} chars) for {doc['title'][:60]}")

            yield record

            # Rate limiting
            time.sleep(1.5)

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Re-fetch all (no incremental API available)."""
        yield from self.fetch_all()

    def test_connection(self) -> bool:
        """Test connectivity to the Lao Trade Portal."""
        try:
            resp = self.session.get(LISTING_URL, timeout=15)
            resp.raise_for_status()
            if "datatable_search_legal" in resp.text:
                logger.info("Connection OK: listing page accessible")
                return True
            else:
                logger.error("Page loaded but datatable not found")
                return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False


def main():
    scraper = LaoTradePortalScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        if sample:
            sample_dir = Path(__file__).parent / "sample"
            sample_dir.mkdir(exist_ok=True)

            count = 0
            total_text = 0
            for record in scraper.fetch_all(sample=True):
                text_len = len(record.get("text", ""))
                total_text += text_len
                count += 1

                # Save sample
                fname = re.sub(r"[^\w\-.]", "_", record["_id"]) + ".json"
                with open(sample_dir / fname, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)

                logger.info(f"  Saved: {fname} ({text_len:,} chars)")

            avg = total_text // count if count else 0
            logger.info(f"Done: {count} records, avg text {avg:,} chars")
        else:
            # Full fetch -- stream every record to data/records.jsonl so the
            # ingest pipeline picks up the whole corpus (not just samples).
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = data_dir / "records.jsonl"

            count = 0
            total_text = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in scraper.fetch_all(sample=False):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_text += len(record.get("text", ""))
                    count += 1
                    if count % 25 == 0:
                        logger.info(f"  Written {count} records -> {jsonl_path}")

            avg = total_text // count if count else 0
            logger.info(f"Done: {count} records written to {jsonl_path}, avg text {avg:,} chars")

    elif command == "update":
        for record in scraper.fetch_updates(""):
            pass

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
