#!/usr/bin/env python3
"""
BQ/Courts -- Caribbean Netherlands (Bonaire, Sint Eustatius, Saba) Court Decisions

Fetches first-instance court decisions for the BES islands from the Dutch
Rechtspraak Open Data API. Targets the BES-specific Gerecht in eerste aanleg
(court of first instance), which is NOT covered by CW/Courts (that source pulls
the shared Gemeenschappelijk Hof appellate court and the joint tax/civil-service
boards). Together they give full BES judicial coverage.

Courts covered:
  - GEABES: Gerecht in eerste aanleg van Bonaire, Sint Eustatius en Saba
            (court of first instance for the BES islands, post-2010)
  - GiEAB:  Gerecht in Eerste Aanleg Bonaire (legacy, pre-2010)

API: https://data.rechtspraak.nl/
No authentication required. Public domain (Dutch Open Data).

Usage:
  python bootstrap.py bootstrap            # Full initial pull
  python bootstrap.py bootstrap --sample   # Fetch sample records
  python bootstrap.py bootstrap-fast --full  # VPS alias for full pull
  python bootstrap.py test-api             # Quick API connectivity test
"""

import sys
import re
import html
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, List, Optional
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.BQ.Courts")

API_BASE = "https://data.rechtspraak.nl"
SEARCH_URL = f"{API_BASE}/uitspraken/zoeken"
CONTENT_URL = f"{API_BASE}/uitspraken/content"

# BES-specific first-instance courts (Bonaire, Sint Eustatius, Saba).
# The shared appellate court (GHACSMBES) and joint boards are covered by
# CW/Courts, so this source deliberately targets only the BES trial courts.
BES_COURTS = [
    {
        "code": "OGEABES",
        "name": "Gerecht in eerste aanleg van Bonaire, Sint Eustatius en Saba",
        "creator": "http://psi.rechtspraak.nl/GEABES",
    },
    {
        "code": "OGEAB",
        "name": "Gerecht in Eerste Aanleg Bonaire (legacy)",
        "creator": "http://psi.rechtspraak.nl/GiEAB",
    },
]

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "psi": "http://psi.rechtspraak.nl/",
}

RS_NS = "{http://www.rechtspraak.nl/schema/rechtspraak-1.0}"


class BQCourtsScraper(BaseScraper):
    """Scraper for BQ/Courts -- Caribbean Netherlands (BES) court decisions."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.client = HttpClient(
            base_url=API_BASE,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "application/xml, application/atom+xml, text/xml, */*",
            },
            timeout=60,
        )

    def _search_eclis(
        self,
        creator: str,
        max_results: int = 1000,
        offset: int = 0,
    ) -> List[Dict]:
        """Search ECLI index filtered by court creator URI."""
        self.rate_limiter.wait()
        try:
            resp = self.client.get(
                "/uitspraken/zoeken",
                params={
                    "max": str(max_results),
                    "from": str(offset),
                    "sort": "DESC",
                    "creator": creator,
                    "return": "DOC",
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Search failed for creator {creator}: {e}")
            return []

        results = []
        try:
            root = ET.fromstring(resp.content)
            for entry in root.findall("atom:entry", NAMESPACES):
                ecli_elem = entry.find("atom:id", NAMESPACES)
                title_elem = entry.find("atom:title", NAMESPACES)
                summary_elem = entry.find("atom:summary", NAMESPACES)
                if ecli_elem is not None and ecli_elem.text:
                    results.append({
                        "ecli": ecli_elem.text,
                        "title": title_elem.text if title_elem is not None else "",
                        "summary": summary_elem.text if summary_elem is not None else "",
                    })
        except ET.ParseError as e:
            logger.error(f"Failed to parse search results: {e}")

        return results

    def _fetch_document(self, ecli: str) -> Optional[str]:
        """Fetch full XML document for an ECLI."""
        self.rate_limiter.wait()
        try:
            resp = self.client.get(
                "/uitspraken/content",
                params={"id": ecli},
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"Failed to fetch {ecli}: {e}")
            return None

    def _extract_text_recursive(self, elem: ET.Element) -> str:
        """Recursively extract all text from an XML element."""
        texts = []
        if elem.text:
            texts.append(elem.text.strip())
        for child in elem:
            child_text = self._extract_text_recursive(child)
            if child_text:
                texts.append(child_text)
            if child.tail:
                texts.append(child.tail.strip())
        full_text = " ".join(t for t in texts if t)
        full_text = html.unescape(full_text)
        full_text = re.sub(r"\s+", " ", full_text)
        return full_text.strip()

    def _parse_document(self, xml_content: str) -> Dict:
        """Parse a Rechtspraak XML document into structured data."""
        try:
            root = ET.fromstring(xml_content.encode("utf-8"))
        except ET.ParseError as e:
            logger.warning(f"XML parse error: {e}")
            return {}

        result = {}

        # RDF metadata
        rdf = root.find(".//rdf:RDF", NAMESPACES)
        if rdf is not None:
            desc = rdf.find("rdf:Description", NAMESPACES)
            if desc is not None:
                for field in ["identifier", "title", "date", "issued", "modified",
                              "creator", "publisher", "type"]:
                    elem = desc.find(f"dcterms:{field}", NAMESPACES)
                    if elem is not None and elem.text:
                        result[field] = elem.text.strip()

                # Multi-valued fields
                for field in ["subject", "procedure"]:
                    vals = []
                    for elem in desc.findall(f"dcterms:{field}", NAMESPACES):
                        if elem.text:
                            vals.append(elem.text.strip())
                    if vals:
                        result[field] = vals

        # Extract full text
        text_parts = []
        for tag in ["inhoudsindicatie", "uitspraak", "conclusie"]:
            elem = root.find(f".//{RS_NS}{tag}")
            if elem is None:
                elem = root.find(f".//{tag}")
            if elem is not None:
                text = self._extract_text_recursive(elem)
                if text and text != "-":
                    label = tag.upper()
                    text_parts.append(f"=== {label} ===\n{text}")

        result["text"] = "\n\n".join(text_parts)
        return result

    def normalize(self, raw: dict) -> dict:
        ecli = raw.get("identifier") or raw.get("ecli", "")
        date = raw.get("date") or raw.get("issued") or ""
        title = raw.get("title") or raw.get("_search_title") or ecli

        subjects = raw.get("subject", [])
        if isinstance(subjects, list):
            subjects = ", ".join(subjects)

        procedures = raw.get("procedure", [])
        if isinstance(procedures, list):
            procedures = ", ".join(procedures)

        return {
            "_id": ecli,
            "_source": "BQ/Courts",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": raw.get("text", ""),
            "date": date,
            "url": f"https://uitspraken.rechtspraak.nl/details?id={ecli}" if ecli else "",
            "ecli": ecli,
            "court": raw.get("creator", ""),
            "court_code": raw.get("_court_code", ""),
            "subject": subjects,
            "procedure": procedures,
            "type": raw.get("type", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        limit = 15 if sample else None
        count = 0

        for court in BES_COURTS:
            if limit and count >= limit:
                break

            code = court["code"]
            creator = court["creator"]
            logger.info(f"Fetching from {code}: {court['name']}")

            offset = 0
            batch_size = 1000

            while True:
                if limit and count >= limit:
                    break

                results = self._search_eclis(creator, max_results=batch_size, offset=offset)
                if not results:
                    break

                for item in results:
                    if limit and count >= limit:
                        break

                    ecli = item.get("ecli")
                    if not ecli:
                        continue

                    xml_content = self._fetch_document(ecli)
                    if not xml_content:
                        continue

                    parsed = self._parse_document(xml_content)
                    if not parsed or not parsed.get("text") or len(parsed["text"]) < 50:
                        continue

                    parsed["ecli"] = ecli
                    parsed["_search_title"] = item.get("title", "")
                    parsed["_court_code"] = code
                    yield parsed
                    count += 1
                    logger.info(f"  [{count}] {ecli} ({len(parsed['text'])} chars)")

                offset += batch_size
                time.sleep(1)

        logger.info(f"Total records yielded: {count}")

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        yield from self.fetch_all()


if __name__ == "__main__":
    scraper = BQCourtsScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test-api] [--sample|--full]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv

    if command == "test-api":
        print("Testing Rechtspraak API for BES courts...")
        for court in BES_COURTS:
            results = scraper._search_eclis(court["creator"], max_results=5)
            print(f"  {court['code']}: {len(results)} results")
            if results:
                ecli = results[0]["ecli"]
                xml = scraper._fetch_document(ecli)
                if xml:
                    parsed = scraper._parse_document(xml)
                    print(f"    Sample: {ecli}, text_len={len(parsed.get('text', ''))}")
        print("Test PASSED")
    elif command in ("bootstrap", "bootstrap-fast"):
        scraper.bootstrap(sample_mode=sample_mode)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
