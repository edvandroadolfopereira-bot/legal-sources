#!/usr/bin/env python3
"""
INTL/IFC-CAO -- IFC/MIGA Compliance Advisor Ombudsman Cases

Fetches case data from the CAO website (cao-ombudsman.org).

Strategy:
  1. Get case page URLs from sitemap.xml
  2. For each case page, scrape metadata and PDF document links
  3. Download the primary English-language report PDF
  4. Extract full text from PDF using PyMuPDF (fitz)
  ~84 cases with documents, ~255 total in CSV index

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py update             # Fetch recent records
  python bootstrap.py test               # Quick connectivity test
"""

import io
import re
import sys
import csv
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, List
from urllib.parse import urljoin

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.IFC-CAO")

BASE_URL = "https://www.cao-ombudsman.org"
CSV_URL = f"{BASE_URL}/export-all-cases"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
DELAY = 2.0

# Priority order for PDF report selection (prefer investigation/assessment)
REPORT_PRIORITY = [
    "compliance investigation report",
    "compliance appraisal report",
    "assessment report",
    "conclusion report",
    "terms of reference",
    "mediation agreement",
    "management action plan",
]


class IFCCAOScraper(BaseScraper):
    SOURCE_ID = "INTL/IFC-CAO"

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; +https://github.com/worldwidelaw/legal-sources)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _get_case_urls_from_sitemap(self) -> List[str]:
        """Get all case page URLs from the sitemap."""
        r = self.session.get(SITEMAP_URL, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.text.strip()
            if "/case/" in url:
                # Fix misconfigured Drupal base URL
                url = re.sub(r"^https?://default/", f"{BASE_URL}/", url)
                urls.append(url)
        logger.info("Sitemap: found %d case URLs", len(urls))
        return urls

    def _get_csv_metadata(self) -> Dict[str, dict]:
        """Download CSV export and index by case name."""
        r = self.session.get(CSV_URL, timeout=30)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        index = {}
        for row in reader:
            name = row.get("Case Name", "").strip()
            if name:
                index[name.lower()] = row
        logger.info("CSV: loaded %d case metadata rows", len(index))
        return index

    # ------------------------------------------------------------------ #
    # Case page scraping
    # ------------------------------------------------------------------ #

    def _scrape_case_page(self, url: str) -> Optional[dict]:
        """Scrape a single case page for metadata and PDF links."""
        try:
            r = self.session.get(url, timeout=30)
            if r.status_code != 200:
                logger.warning("Case page %s returned %d", url, r.status_code)
                return None
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""
        # Remove site suffix
        title = re.sub(r"\s*\|.*$", "", raw_title).strip()

        # Extract slug
        slug = url.rstrip("/").split("/case/")[-1] if "/case/" in url else ""

        # Find all PDF links
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                label = a.get_text(strip=True)
                full_url = urljoin(BASE_URL, href)
                pdfs.append({"label": label, "url": full_url})

        # Deduplicate PDFs by URL
        seen = set()
        unique_pdfs = []
        for p in pdfs:
            if p["url"] not in seen:
                seen.add(p["url"])
                unique_pdfs.append(p)

        return {
            "title": title,
            "slug": slug,
            "url": url,
            "pdfs": unique_pdfs,
        }

    def _select_best_pdf(self, pdfs: List[dict]) -> Optional[dict]:
        """Select the best English-language report PDF."""
        if not pdfs:
            return None

        # Filter for English PDFs only
        english_pdfs = []
        for p in pdfs:
            label = p["label"].lower()
            url = p["url"].lower()
            # Skip non-English translations
            if any(lang in label for lang in [
                "kinyarwanda", "arabic", "français", "french", "spanish",
                "español", "português", "swahili", "pular",
            ]):
                continue
            if any(lang in url for lang in [
                "kinyarwanda", "arabic", "french", "spanish", "portuguese",
            ]):
                continue
            english_pdfs.append(p)

        if not english_pdfs:
            english_pdfs = pdfs  # fallback to all if no English found

        # Prioritize by report type
        for priority_term in REPORT_PRIORITY:
            for p in english_pdfs:
                if priority_term in p["label"].lower():
                    return p

        # Default to first English PDF
        return english_pdfs[0]

    # ------------------------------------------------------------------ #
    # PDF text extraction
    # ------------------------------------------------------------------ #

    def _extract_pdf_text(self, url: str) -> Optional[str]:
        """Download a PDF and extract full text using PyMuPDF."""
        try:
            r = self.session.get(url, timeout=120, stream=True)
            r.raise_for_status()

            # Safety: skip PDFs > 50MB
            content_length = r.headers.get("Content-Length")
            if content_length and int(content_length) > 50_000_000:
                logger.warning("PDF too large (%s bytes): %s", content_length, url)
                return None

            data = r.content
            if len(data) < 100:
                logger.warning("PDF too small (%d bytes): %s", len(data), url)
                return None

            doc = fitz.open(stream=data, filetype="pdf")
            text_parts = []
            for page in doc:
                t = page.get_text()
                if t:
                    text_parts.append(t)
            doc.close()

            text = "\n".join(text_parts).strip()
            if len(text) < 50:
                logger.warning("PDF extraction yielded only %d chars: %s", len(text), url)
                return None

            return text

        except Exception as e:
            logger.warning("PDF extraction failed for %s: %s", url, e)
            return None

    # ------------------------------------------------------------------ #
    # Normalization
    # ------------------------------------------------------------------ #

    def normalize(self, raw: dict) -> dict:
        """Abstract method implementation — delegates to _normalize."""
        return self._normalize(raw, None)

    def _normalize(self, case_data: dict, csv_meta: Optional[dict]) -> dict:
        """Normalize a case record into standard schema."""
        now = datetime.now(timezone.utc).isoformat()

        # Parse date from CSV metadata
        date = None
        if csv_meta and csv_meta.get("Last Updated"):
            try:
                raw_date = csv_meta["Last Updated"]
                # Format: "Thu, 05/07/2026 - 12:00"
                m = re.search(r"(\d{2}/\d{2}/\d{4})", raw_date)
                if m:
                    dt = datetime.strptime(m.group(1), "%m/%d/%Y")
                    date = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                pass

        record = {
            "_id": f"CAO-{case_data['slug']}",
            "_source": self.SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": now,
            "title": case_data["title"],
            "text": case_data.get("text", ""),
            "date": date,
            "url": case_data["url"],
            "case_slug": case_data["slug"],
            "pdf_url": case_data.get("pdf_url"),
            "pdf_count": len(case_data.get("pdfs", [])),
        }

        # Add CSV metadata fields if available
        if csv_meta:
            record["status"] = csv_meta.get("Status", "")
            record["region"] = csv_meta.get("Region", "")
            record["country"] = csv_meta.get("Country", "")
            record["phase"] = csv_meta.get("Phase", "")
            record["institution"] = csv_meta.get("Institution (IFC, MIGA, IFC/MIGA)", "")
            record["project"] = csv_meta.get("Name and Number (Project number)", "")
            record["company"] = csv_meta.get("Company (IFC/MIGA Client)", "")
            record["sector"] = csv_meta.get("Sector", "")
            record["complainant"] = csv_meta.get("Complainant", "")
            record["cross_cutting_issues"] = csv_meta.get("Cross-cutting issues", "")

        return record

    # ------------------------------------------------------------------ #
    # Main fetch logic
    # ------------------------------------------------------------------ #

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:  # type: ignore[override]
        """Fetch all CAO cases with full text from PDF reports."""
        # Step 1: Get case URLs from sitemap
        case_urls = self._get_case_urls_from_sitemap()
        if not case_urls:
            logger.error("No case URLs found in sitemap")
            return

        # Step 2: Get CSV metadata for enrichment
        csv_meta = self._get_csv_metadata()

        limit = 15 if sample else len(case_urls)
        count = 0
        skipped = 0

        for url in case_urls[:limit]:
            time.sleep(DELAY)

            # Scrape case page
            case_data = self._scrape_case_page(url)
            if not case_data:
                skipped += 1
                continue

            # Select best PDF and extract text
            best_pdf = self._select_best_pdf(case_data["pdfs"])
            if best_pdf:
                time.sleep(DELAY)
                text = self._extract_pdf_text(best_pdf["url"])
                if text:
                    case_data["text"] = text
                    case_data["pdf_url"] = best_pdf["url"]
                    logger.info(
                        "Extracted %d chars from %s (%s)",
                        len(text), case_data["slug"], best_pdf["label"],
                    )
                else:
                    logger.warning("No text extracted for %s", case_data["slug"])
                    case_data["text"] = ""
                    case_data["pdf_url"] = best_pdf["url"]
            else:
                logger.warning("No PDFs found for %s", case_data["slug"])
                case_data["text"] = ""
                case_data["pdf_url"] = None

            # Skip cases with no text
            if not case_data.get("text"):
                skipped += 1
                continue

            # Match CSV metadata
            title_lower = case_data["title"].lower()
            matched_csv = csv_meta.get(title_lower)

            record = self._normalize(case_data, matched_csv)
            count += 1
            yield record

        logger.info(
            "Done: %d records yielded, %d skipped (no text), %d total URLs",
            count, skipped, len(case_urls),
        )

    def fetch_updates(self, since) -> Generator[dict, None, None]:
        """Fetch cases updated since a given date."""
        # Re-run full fetch — small dataset, no incremental API
        yield from self.fetch_all(sample=False)

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        try:
            r = self.session.get(CSV_URL, timeout=15)
            return r.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------- #
# CLI entry point
# ---------------------------------------------------------------------- #

def main():
    scraper = IFCCAOScraper()
    args = sys.argv[1:]

    if not args or args[0] == "test":
        ok = scraper.test_connection()
        print(f"Connection test: {'OK' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)

    sample = "--sample" in args
    command = args[0]

    if command == "bootstrap":
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)
        count = 0
        for record in scraper.fetch_all(sample=sample):
            count += 1
            out_path = sample_dir / f"{count:04d}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            text_len = len(record.get("text", ""))
            logger.info(
                "[%d] %s — %d chars",
                count, record["title"], text_len,
            )
        print(f"\nBootstrap complete: {count} records saved to sample/")

    elif command in ("update", "bootstrap-fast"):
        since = args[1] if len(args) > 1 else "2020-01-01"
        count = 0
        for record in scraper.fetch_updates(since):
            count += 1
            print(json.dumps(record, ensure_ascii=False))
        logger.info("Update complete: %d records", count)

    else:
        print(f"Unknown command: {command}")
        print("Usage: bootstrap.py [bootstrap|update|test] [--sample]")
        sys.exit(1)


if __name__ == "__main__":
    main()
