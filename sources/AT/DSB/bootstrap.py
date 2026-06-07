#!/usr/bin/env python3
"""
AT/DSB -- Austrian Data Protection Authority (Datenschutzbehörde) Decisions

Fetches GDPR/data protection decisions from the RIS OGD API v2.6,
using the "Dsk" (Datenschutz-Aufsichtsbehörden) application.

1,854 decisions available. Same API as AT/RIS but separate application.

Usage:
  python bootstrap.py bootstrap            # Full pull (~1,854 records)
  python bootstrap.py bootstrap --sample   # Sample records for validation
  python bootstrap.py bootstrap-fast       # Concurrent full-text download
  python bootstrap.py update               # Incremental update (last month)
"""

import sys
import json
import logging
import time
import re
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.AT.DSB")

API_BASE = "https://data.bka.gv.at/ris/api/v2.6"
APPLICATION = "Dsk"


class DSBScraper(BaseScraper):
    """
    Scraper for AT/DSB — Austrian Data Protection Authority decisions.
    Uses the RIS OGD API v2.6, Dsk application.
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=API_BASE,
            headers={"User-Agent": "LegalDataHunter/1.0 (Open Data Research)"},
            timeout=60,
        )

    def _paginate(self, extra_params=None, max_pages=None):
        """Paginate through the Dsk application endpoint."""
        page = 1
        total_hits = None

        while True:
            if max_pages and page > max_pages:
                return

            params = {
                "Applikation": APPLICATION,
                "DokumenteProSeite": "OneHundred",
                "Seitennummer": str(page),
            }
            if extra_params:
                params.update(extra_params)

            self.rate_limiter.wait()
            try:
                resp = self.client.get("/Judikatur", params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"API error on page {page}: {e}")
                time.sleep(5)
                try:
                    resp = self.client.get("/Judikatur", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e2:
                    logger.error(f"Retry failed: {e2}")
                    return

            search_result = data.get("OgdSearchResult", {})
            doc_results = search_result.get("OgdDocumentResults", {})

            if total_hits is None:
                hits_info = doc_results.get("Hits", {})
                try:
                    total_hits = int(hits_info.get("#text", "0"))
                except (ValueError, TypeError):
                    total_hits = 0
                logger.info(f"DSB decisions: {total_hits} total hits")
                if total_hits == 0:
                    return

            docs = doc_results.get("OgdDocumentReference", [])
            if not isinstance(docs, list):
                docs = [docs] if docs else []
            if not docs:
                return

            for doc in docs:
                doc_data = doc.get("Data", {})
                if doc_data:
                    yield doc_data

            fetched_so_far = page * 100
            if fetched_so_far >= total_hits:
                logger.info(f"Fetched all {total_hits} DSB decisions")
                return

            page += 1
            logger.info(f"  Page {page} ({fetched_so_far}/{total_hits})")

    def _flatten_item(self, obj):
        """Normalize RIS item wrappers to string."""
        if not obj:
            return ""
        if isinstance(obj, str):
            return obj
        item = obj.get("item", "")
        if isinstance(item, list):
            parts = []
            for i in item:
                if isinstance(i, dict):
                    parts.append(json.dumps(i, ensure_ascii=False))
                else:
                    parts.append(str(i))
            return " | ".join(parts)
        if isinstance(item, dict):
            return json.dumps(item, ensure_ascii=False)
        return str(item)

    def _extract_content_urls(self, raw):
        """Extract document content URLs from API response."""
        urls = {}
        doc_liste = raw.get("Dokumentliste", {})
        content_refs = doc_liste.get("ContentReference", [])
        if not isinstance(content_refs, list):
            content_refs = [content_refs] if content_refs else []

        for cr in content_refs:
            content_urls = cr.get("Urls", {}).get("ContentUrl", [])
            if not isinstance(content_urls, list):
                content_urls = [content_urls] if content_urls else []
            for cu in content_urls:
                dtype = cu.get("DataType", "")
                url = cu.get("Url", "")
                if dtype and url:
                    urls[dtype.lower()] = url
        return urls

    def _download_full_text(self, content_urls):
        """Download and extract full text, preferring XML."""
        xml_url = content_urls.get("xml")
        if xml_url:
            try:
                self.rate_limiter.wait()
                resp = self.client.get(xml_url)
                resp.raise_for_status()

                root = ET.fromstring(resp.content)
                text_parts = []
                ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""

                for absatz in root.iter(f"{ns}absatz" if ns else "absatz"):
                    text = "".join(absatz.itertext()).strip()
                    if text:
                        text_parts.append(text)

                if not text_parts and ns:
                    for absatz in root.iter("absatz"):
                        text = "".join(absatz.itertext()).strip()
                        if text:
                            text_parts.append(text)

                if not text_parts:
                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                        if tag in ["titel", "untertitel", "absatz", "text", "betreff"]:
                            text = "".join(elem.itertext()).strip()
                            if text:
                                text_parts.append(text)

                full_text = "\n\n".join(text_parts)
                full_text = html.unescape(full_text)
                full_text = re.sub(r"\s+", " ", full_text).strip()

                if full_text:
                    return full_text
            except Exception as e:
                logger.warning(f"XML fetch failed for {xml_url}: {e}")

        html_url = content_urls.get("html")
        if html_url:
            try:
                self.rate_limiter.wait()
                resp = self.client.get(html_url)
                resp.raise_for_status()
                text = resp.text
                text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = html.unescape(text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"HTML fetch failed for {html_url}: {e}")

        return ""

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all DSB decisions."""
        logger.info("Fetching all DSB decisions from RIS API (Dsk application)")
        for doc in self._paginate():
            yield doc

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield DSB decisions modified since the given date."""
        days_ago = (datetime.now(timezone.utc) - since).days
        if days_ago <= 7:
            im_ris_seit = "EinerWoche"
        elif days_ago <= 14:
            im_ris_seit = "ZweiWochen"
        elif days_ago <= 30:
            im_ris_seit = "EinemMonat"
        elif days_ago <= 90:
            im_ris_seit = "DreiMonaten"
        elif days_ago <= 180:
            im_ris_seit = "SechsMonaten"
        else:
            im_ris_seit = "EinemJahr"

        logger.info(f"Fetching DSB updates ({im_ris_seit})")
        for doc in self._paginate(extra_params={"ImRisSeit": im_ris_seit}):
            yield doc

    def normalize(self, raw: dict) -> dict:
        """Transform raw RIS DSK response into standard schema."""
        meta = raw.get("Metadaten", {})
        tech = meta.get("Technisch", {})
        allg = meta.get("Allgemein", {})
        jud = meta.get("Judikatur", {})
        dsk = jud.get("Dsk", {})

        doc_id = tech.get("ID", "")
        geschaeftszahl = self._flatten_item(jud.get("Geschaeftszahl", {}))
        normen = self._flatten_item(jud.get("Normen", {}))
        entscheidungsdatum = jud.get("Entscheidungsdatum", "")
        ecli = jud.get("EuropeanCaseLawIdentifier", "")
        schlagworte = jud.get("Schlagworte", "")

        entscheidungsart = dsk.get("Entscheidungsart", "")
        kurzinformation = dsk.get("Kurzinformation", "")
        entscheidende_behoerde = dsk.get("EntscheidendeBehoerde", "")
        anfechtung = dsk.get("Anfechtung", "")

        content_urls = self._extract_content_urls(raw)
        full_text = ""
        if content_urls:
            full_text = self._download_full_text(content_urls)

        document_url = allg.get("DokumentUrl", "")
        title = geschaeftszahl or doc_id

        date = entscheidungsdatum or allg.get("Geaendert", "")

        return {
            "_id": doc_id,
            "_source": "AT/DSB",
            "_type": "doctrine",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": full_text,
            "date": date,
            "url": document_url,
            "ecli": ecli,
            "geschaeftszahl": geschaeftszahl,
            "normen": normen,
            "schlagworte": schlagworte,
            "entscheidungsart": entscheidungsart,
            "kurzinformation": kurzinformation,
            "entscheidende_behoerde": entscheidende_behoerde,
            "anfechtung": anfechtung,
            "organ": tech.get("Organ", ""),
        }


def main():
    scraper = DSBScraper()

    import argparse

    parser = argparse.ArgumentParser(description="AT/DSB Data Protection Decisions Fetcher")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update"],
        help="Command to run",
    )
    parser.add_argument("--sample", action="store_true", help="Sample mode (few records)")
    parser.add_argument("--sample-size", type=int, default=15, help="Number of sample records")
    parser.add_argument("--workers", type=int, default=None, help="Concurrent threads (bootstrap-fast)")
    parser.add_argument("--batch-size", type=int, default=100, help="Records per batch (bootstrap-fast)")
    parser.add_argument("--full", action="store_true", help="Fetch all records")

    args = parser.parse_args()

    if args.command == "bootstrap":
        if args.sample:
            stats = scraper.run_sample(n=args.sample_size)
            print(
                f"\nSample complete: "
                f"{stats.get('sample_records_saved', 0)} records saved to sample/"
            )
        else:
            stats = scraper.bootstrap()
            print(
                f"\nBootstrap complete: {stats['records_new']} new, "
                f"{stats['records_updated']} updated, "
                f"{stats['records_skipped']} skipped"
            )
        print(json.dumps(stats, indent=2))

    elif args.command == "bootstrap-fast":
        stats = scraper.bootstrap_fast(
            max_workers=args.workers,
            batch_size=args.batch_size,
        )
        print(f"\nFast bootstrap complete: {stats['records_new']} new, "
              f"{stats['records_updated']} updated, "
              f"{stats['errors']} errors")
        print(json.dumps(stats, indent=2))

    elif args.command == "update":
        stats = scraper.update()
        print(
            f"\nUpdate complete: {stats['records_new']} new, "
            f"{stats['records_updated']} updated"
        )
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
