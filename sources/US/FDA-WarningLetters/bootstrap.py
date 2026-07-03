#!/usr/bin/env python3
"""
US/FDA-WarningLetters -- FDA Warning Letters

Fetches FDA warning letters via Playwright (Akamai bot protection blocks requests).
~3,500 warning letters with full text, metadata, and compliance details.

Data access:
  - Listing page with DataTables pagination at fda.gov warning-letters page
  - Individual letter pages with full HTML body text + metadata sidebar
  - Requires Playwright (Chromium) due to Akamai bot detection on fda.gov

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.US.FDA-WarningLetters")

BASE_URL = "https://www.fda.gov"
LISTING_URL = (
    BASE_URL
    + "/inspections-compliance-enforcement-and-criminal-investigations"
    "/compliance-actions-and-activities/warning-letters"
)
DELAY = 2.0
SOURCE_ID = "US/FDA-WarningLetters"


def parse_date(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def clean_text(text: str) -> str:
    text = re.sub(r"\xa0", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class FDAWarningLettersScraper:
    SOURCE_ID = SOURCE_ID

    def __init__(self):
        self._browser = None
        self._context = None
        self._playwright = None

    def _start_browser(self):
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    def _stop_browser(self):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._context = None
        self._playwright = None

    def _fetch_page(self, url: str, wait_selector: str = None, timeout: int = 30000) -> Optional[Any]:
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout)
            return page
        except Exception as e:
            logger.warning("Failed to load %s: %s", url, e)
            page.close()
            return None

    def collect_listing_urls(self, max_entries: int = 0) -> List[Dict[str, str]]:
        """Load the listing page and paginate through DataTables to collect all letter URLs."""
        self._start_browser()
        entries = []

        page = self._fetch_page(LISTING_URL, wait_selector="table tbody tr", timeout=60000)
        if not page:
            logger.error("Cannot load listing page")
            return []

        try:
            # Get total count
            info_el = page.query_selector(".dataTables_info")
            total_text = info_el.inner_text() if info_el else ""
            total_match = re.search(r"of ([\d,]+) entries", total_text)
            total = int(total_match.group(1).replace(",", "")) if total_match else 0
            logger.info("Total warning letters: %d", total)

            # Set page size to 100
            try:
                page.select_option('select[name="datatable_length"]', "100")
                time.sleep(3)
                page.wait_for_selector("table tbody tr", timeout=15000)
            except Exception:
                logger.warning("Could not set page size to 100, using default")

            page_num = 0
            while True:
                rows = page.query_selector_all("table tbody tr")
                if not rows:
                    break

                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) < 5:
                        continue

                    link = row.query_selector("a")
                    if not link:
                        continue

                    href = link.get_attribute("href") or ""
                    company = link.inner_text().strip()

                    posted_date = cells[0].inner_text().strip()
                    issue_date = cells[1].inner_text().strip()
                    issuing_office = cells[3].inner_text().strip() if len(cells) > 3 else ""
                    subject = cells[4].inner_text().strip() if len(cells) > 4 else ""

                    if href:
                        full_url = BASE_URL + href if href.startswith("/") else href
                        entries.append({
                            "url": full_url,
                            "company": company,
                            "posted_date": posted_date,
                            "issue_date": issue_date,
                            "issuing_office": issuing_office,
                            "subject": subject,
                        })

                logger.info(
                    "Page %d: collected %d entries (total so far: %d)",
                    page_num, len(rows), len(entries),
                )

                if max_entries and len(entries) >= max_entries:
                    entries = entries[:max_entries]
                    break

                # Try to go to next page
                next_a = page.query_selector("#datatable_next:not(.disabled) a")
                if not next_a:
                    break

                next_a.click()
                time.sleep(DELAY)
                try:
                    page.wait_for_selector("table tbody tr", timeout=15000)
                except Exception:
                    break

                page_num += 1
        finally:
            page.close()

        return entries

    def fetch_letter_detail(self, url: str) -> Dict[str, Any]:
        """Fetch a single warning letter page and extract full text + metadata."""
        page = self._fetch_page(url, wait_selector="article", timeout=30000)
        if not page:
            return {}

        try:
            meta: Dict[str, Any] = {
                "body_text": "",
                "delivery_method": "",
                "product_type": "",
                "recipient": "",
                "issuing_office": "",
                "marcs_id": "",
            }

            # Extract main body text from article
            article = page.query_selector("article")
            if article:
                meta["body_text"] = clean_text(article.inner_text())

            # Extract structured metadata from description lists
            dl_items = page.query_selector_all("dl")
            for dl in dl_items:
                dts = dl.query_selector_all("dt")
                dds = dl.query_selector_all("dd")
                for dt, dd in zip(dts, dds):
                    label = dt.inner_text().strip().lower().rstrip(":")
                    value = dd.inner_text().strip()
                    if "delivery method" in label:
                        meta["delivery_method"] = value
                    elif "product" in label:
                        meta["product_type"] = value
                    elif "recipient" in label:
                        meta["recipient"] = value
                    elif "issuing office" in label:
                        meta["issuing_office"] = value

            # Extract MARCS ID from title or content
            title = page.title() or ""
            marcs_match = re.search(r"(\d{6})", title)
            if marcs_match:
                meta["marcs_id"] = marcs_match.group(1)

            return meta
        finally:
            page.close()

    def normalize(
        self, listing_item: Dict[str, str], detail: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize into standard schema."""
        url = listing_item["url"]
        slug = url.rstrip("/").split("/")[-1]

        # Build ID from MARCS number or slug
        marcs_id = detail.get("marcs_id", "")
        doc_id = f"fda-wl-{marcs_id}" if marcs_id else f"fda-wl-{slug}"

        date = parse_date(listing_item.get("issue_date", ""))
        text = detail.get("body_text", "").strip()

        # Use detail metadata if available, fall back to listing
        issuing_office = (
            detail.get("issuing_office", "") or listing_item.get("issuing_office", "")
        )

        return {
            "_id": doc_id,
            "_source": self.SOURCE_ID,
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": listing_item.get("company", slug),
            "text": text,
            "date": date,
            "url": url,
            "issuing_office": issuing_office,
            "subject": listing_item.get("subject", ""),
            "recipient": detail.get("recipient", ""),
            "delivery_method": detail.get("delivery_method", ""),
            "product_type": detail.get("product_type", ""),
            "posted_date": parse_date(listing_item.get("posted_date", "")),
            "marcs_id": marcs_id,
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Fetch all warning letters (or a sample of 15)."""
        self._start_browser()
        try:
            max_entries = 15 if sample else 0
            listings = self.collect_listing_urls(max_entries=max_entries)
            logger.info("Collected %d listing entries", len(listings))

            for i, item in enumerate(listings):
                logger.info(
                    "[%d/%d] Fetching: %s", i + 1, len(listings), item["company"]
                )
                time.sleep(DELAY)
                detail = self.fetch_letter_detail(item["url"])
                if not detail or not detail.get("body_text"):
                    logger.warning("No body text for %s, skipping", item["url"])
                    continue

                record = self.normalize(item, detail)
                if record["text"]:
                    yield record
                else:
                    logger.warning("Empty text after normalize for %s", item["url"])
        finally:
            self._stop_browser()

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch warning letters posted since a date (ISO format)."""
        since_dt = datetime.fromisoformat(since)
        self._start_browser()
        try:
            # Load first few pages of newest letters
            listings = self.collect_listing_urls(max_entries=200)
            for i, item in enumerate(listings):
                posted = parse_date(item.get("posted_date", ""))
                if posted and datetime.fromisoformat(posted) < since_dt:
                    logger.info("Reached letters before %s, stopping", since)
                    break

                logger.info("[%d] Fetching update: %s", i + 1, item["company"])
                time.sleep(DELAY)
                detail = self.fetch_letter_detail(item["url"])
                if not detail or not detail.get("body_text"):
                    continue
                record = self.normalize(item, detail)
                if record["text"]:
                    yield record
        finally:
            self._stop_browser()

    def test_connection(self) -> bool:
        """Quick test that the site is accessible."""
        self._start_browser()
        try:
            page = self._fetch_page(LISTING_URL, wait_selector="table", timeout=30000)
            if not page:
                return False
            info = page.query_selector(".dataTables_info")
            if info:
                logger.info("Connection OK: %s", info.inner_text())
                page.close()
                return True
            page.close()
            return False
        finally:
            self._stop_browser()


def save_samples(records: List[Dict[str, Any]], sample_dir: Path):
    sample_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        fname = re.sub(r"[^a-zA-Z0-9_-]", "_", rec["_id"])[:80] + ".json"
        path = sample_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d samples to %s", len(records), sample_dir)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0]
    # `bootstrap-fast` is the VPS full-run entrypoint — it must run FULL, not
    # sample mode. Only an explicit --sample flag triggers sample mode.
    sample_mode = "--sample" in args
    source_dir = Path(__file__).parent
    sample_dir = source_dir / "sample"

    scraper = FDAWarningLettersScraper()

    if command == "test":
        ok = scraper.test_connection()
        print("OK" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        # Full runs stream each record to data/records.jsonl as it is fetched
        # (the path the VPS pipeline ingests) so we never hold the whole corpus
        # in memory and the full dataset actually lands. Sample runs collect a
        # handful and write them to sample/ for validation.
        records = []
        out_path = None
        out_f = None
        if not sample_mode:
            data_dir = source_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            out_path = data_dir / "records.jsonl"
            out_f = open(out_path, "w", encoding="utf-8")

        count = 0
        total_chars = 0
        try:
            for record in scraper.fetch_all(sample=sample_mode):
                count += 1
                total_chars += len(record["text"])
                logger.info(
                    "Record %d: %s (%d chars text)",
                    count,
                    record["title"],
                    len(record["text"]),
                )
                if sample_mode:
                    records.append(record)
                    if len(records) >= 15:
                        break
                else:
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()
        finally:
            if out_f is not None:
                out_f.close()

        if sample_mode:
            save_samples(records, sample_dir)
        else:
            logger.info("Wrote %d records to %s", count, out_path)

        logger.info(
            "Done: %d records, avg text length: %d chars",
            count,
            total_chars // max(count, 1),
        )

    elif command == "update":
        since = args[1] if len(args) > 1 else "2026-01-01"
        records = list(scraper.fetch_updates(since))
        out_path = source_dir / "updates.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info("Wrote %d update records to %s", len(records), out_path)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
