#!/usr/bin/env python3
"""
NL/Tuchtrecht -- Dutch Professional Disciplinary Tribunal Decisions

Fetches full-text decisions from Tuchtrecht (tuchtrecht.overheid.nl), the
official Dutch government collection of professional disciplinary case law.
It covers the disciplinary tribunals (tuchtcolleges) and their appellate
bodies for the regulated professions, including:
  - Advocaten (lawyers) -- Raden / Hof van Discipline
  - Gezondheidszorg (healthcare) -- Regionale / Centraal Tuchtcollege
  - Notarissen (civil-law notaries)
  - Gerechtsdeurwaarders (bailiffs)
  - Accountants (Accountantskamer / CBb)
  - Diergeneeskundigen (veterinarians)
  - Scheepvaart (maritime / shipping discipline)

Every decision is ECLI-indexed and carries full reasoning text.

Strategy:
  - List: KOOP SRU 2.0 API over the `tuchtrecht` product-area returns the full
    ECLI index (~47,600 decisions) with per-record metadata and a direct XML
    manifestation URL. Linear pagination via startRecord works to the end of
    the collection (no deep-pagination cap).
  - Full text: GET the XML manifestation; the <uitspraaktekst> element holds the
    full decision body and <inhoudsindicatie> the headnote/summary.

API:
  - SRU search:  https://repository.overheid.nl/sru
                 ?operation=searchRetrieve&version=2.0
                 &query=c.product-area==tuchtrecht
                 &maximumRecords=100&startRecord=N
  - XML doc:     manifestation="xml" itemUrl from each SRU record
                 (e.g. https://repository.overheid.nl/frbr/tuchtrecht/{year}/
                        {ECLI}/1/xml/{ECLI_underscored}.xml)

Usage:
  python bootstrap.py bootstrap           # Full initial pull (~47.6K decisions)
  python bootstrap.py bootstrap-fast      # Alias for bootstrap (VPS runner)
  python bootstrap.py bootstrap --sample  # Fetch sample records for validation
  python bootstrap.py update              # Incremental update (modified since)
  python bootstrap.py test-api            # Quick API connectivity test
"""

import sys
import json
import logging
import re
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List
from xml.etree import ElementTree as ET

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.NL.Tuchtrecht")

# ── API configuration ────────────────────────────────────────────────
SRU_URL = "https://repository.overheid.nl/sru"
PRODUCT_AREA = "tuchtrecht"
PAGE_SIZE = 100  # records per SRU page (max 1000; 100 is friendly + stable)

# SRU response namespaces
SRU_NS = {
    "sru": "http://docs.oasis-open.org/ns/search-ws/sruResponse",
    "gzd": "http://standaarden.overheid.nl/sru",
    "dcterms": "http://purl.org/dc/terms/",
    "c": "http://standaarden.overheid.nl/collectie/",
    "overheidwetgeving": "http://standaarden.overheid.nl/wetgeving/",
}


class TuchtrechtScraper(BaseScraper):
    """
    Scraper for NL/Tuchtrecht -- Dutch professional disciplinary decisions.
    Country: NL
    URL: https://tuchtrecht.overheid.nl

    Data types: case_law
    Auth: none (Dutch government open data via KOOP SRU)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (Open Data Research; legal-data-hunter)",
            "Accept": "application/xml, text/xml, */*;q=0.8",
            "Accept-Language": "nl,en;q=0.9",
        })

    # ── HTTP helpers ──────────────────────────────────────────────────
    def _get(self, url: str, params: dict = None, timeout: int = 60) -> Optional[bytes]:
        """GET a URL with rate limiting; return raw bytes or None."""
        for attempt in range(3):
            try:
                self.rate_limiter.wait()
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                wait = 3 * (attempt + 1)
                logger.warning(f"GET failed ({e}); retry in {wait}s [{url}]")
                import time
                time.sleep(wait)
        logger.error(f"GET permanently failed: {url}")
        return None

    # ── SRU listing ───────────────────────────────────────────────────
    def _iter_sru_records(self, start: int = 1) -> Generator[Dict[str, Any], None, None]:
        """
        Paginate the SRU index, yielding lightweight metadata dicts:
          {ecli, title, type, creator, modified, xml_url, public_url}
        Full text is NOT downloaded here (kept cheap for update filtering).
        """
        position = start
        total = None

        while True:
            params = {
                "operation": "searchRetrieve",
                "version": "2.0",
                "query": f"c.product-area=={PRODUCT_AREA}",
                "maximumRecords": str(PAGE_SIZE),
                "startRecord": str(position),
            }
            content = self._get(SRU_URL, params=params)
            if not content:
                break

            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                logger.error(f"SRU parse error at startRecord={position}: {e}")
                break

            if total is None:
                num = root.find("sru:numberOfRecords", SRU_NS)
                total = int(num.text) if num is not None and num.text else 0
                logger.info(f"SRU reports {total} tuchtrecht decisions")

            records = root.findall(".//sru:record", SRU_NS)
            if not records:
                break

            yielded = 0
            for rec in records:
                meta = self._parse_sru_record(rec)
                if meta and meta.get("xml_url"):
                    yielded += 1
                    yield meta

            # Advance using nextRecordPosition when available
            nxt = root.find("sru:nextRecordPosition", SRU_NS)
            if nxt is not None and nxt.text:
                position = int(nxt.text)
            else:
                position += len(records)

            if total and position > total:
                break
            if yielded == 0 and len(records) == 0:
                break

    def _parse_sru_record(self, rec: ET.Element) -> Optional[Dict[str, Any]]:
        """Extract metadata + the XML manifestation URL from one SRU record."""
        def first_text(path: str) -> str:
            el = rec.find(path, SRU_NS)
            return el.text.strip() if el is not None and el.text else ""

        ecli = first_text(".//dcterms:identifier")
        title = first_text(".//dcterms:title")
        dtype = first_text(".//dcterms:type")
        creator = first_text(".//dcterms:creator")
        modified = first_text(".//dcterms:modified")

        xml_url = ""
        public_url = ""
        for item in rec.findall(".//gzd:itemUrl", SRU_NS):
            if item.get("manifestation") == "xml" and item.text:
                xml_url = item.text.strip()
        pref = rec.find(".//gzd:preferredUrl", SRU_NS)
        if pref is not None and pref.text:
            public_url = pref.text.strip()

        if not ecli:
            return None
        if not public_url:
            public_url = f"https://tuchtrecht.overheid.nl/{ecli}"

        return {
            "ecli": ecli,
            "title": title,
            "type": dtype,
            "creator": creator,
            "modified": modified,
            "xml_url": xml_url,
            "public_url": public_url,
        }

    # ── Full-text document fetch / parse ──────────────────────────────
    def _clean(self, text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _element_text(self, elem: ET.Element) -> str:
        """Recursively collect readable text, using <p> as paragraph breaks."""
        parts: List[str] = []

        def walk(node: ET.Element):
            tag = node.tag.split("}")[-1].lower()
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            for child in node:
                walk(child)
                if child.tail and child.tail.strip():
                    parts.append(child.tail.strip())
            if tag in ("p", "para", "title", "li", "tr"):
                parts.append("\n")

        walk(elem)
        return self._clean(" ".join(parts))

    def _parse_document(self, xml_bytes: bytes) -> Dict[str, Any]:
        """Parse a tuchtrecht XML document into metadata + full text."""
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            logger.warning(f"Document XML parse error: {e}")
            return {}

        def find_local(tag: str) -> Optional[ET.Element]:
            for el in root.iter():
                if el.tag.split("}")[-1] == tag:
                    return el
            return None

        def local_text(tag: str) -> str:
            el = find_local(tag)
            return el.text.strip() if el is not None and el.text else ""

        def iso_date(tag: str) -> str:
            """Build ISO 8601 date from dag/maand/jaar attributes."""
            el = find_local(tag)
            if el is None:
                return ""
            jaar = el.get("jaar")
            maand = el.get("maand")
            dag = el.get("dag")
            if jaar and maand and dag:
                try:
                    return f"{int(jaar):04d}-{int(maand):02d}-{int(dag):02d}"
                except ValueError:
                    pass
            return (el.text or "").strip()

        # <instantie> wraps <domein>, <type> and <plaats>; scope lookups to it
        # because a generic <type> also appears in the document header.
        instantie = find_local("instantie")

        def in_instantie(tag: str) -> str:
            if instantie is None:
                return ""
            for el in instantie.iter():
                if el.tag.split("}")[-1] == tag and el.text:
                    return el.text.strip()
            return ""

        domein = in_instantie("domein")
        doc_type = in_instantie("type")
        plaats = in_instantie("plaats")
        # Readable court name, e.g. "Raad van Discipline Arnhem-Leeuwarden"
        court = " ".join(p for p in (doc_type, plaats) if p).strip()

        result: Dict[str, Any] = {
            "court": court,
            "domein": domein,
            "doc_type": doc_type,
            "plaats": plaats,
            "uitspraakdatum": iso_date("uitspraakdatum"),
            "publicatiedatum": iso_date("publicatiedatum"),
            "arrondissement": local_text("arrondissement"),
        }

        # Zaaknummers (case numbers)
        zaaknummers = [
            (el.text or "").strip()
            for el in root.iter()
            if el.tag.split("}")[-1] == "zaaknummer" and el.text
        ]
        result["zaaknummers"] = [z for z in zaaknummers if z]

        # Onderwerpen (subjects)
        onderwerpen = [
            (el.text or "").strip()
            for el in root.iter()
            if el.tag.split("}")[-1] in ("onderwerp", "subonderwerp") and el.text
        ]
        result["onderwerpen"] = [o for o in onderwerpen if o]

        # Beslissingen (outcomes)
        beslissingen = [
            (el.text or "").strip()
            for el in root.iter()
            if el.tag.split("}")[-1] == "beslissing" and el.text
        ]
        result["beslissingen"] = [b for b in beslissingen if b]

        # Full text: inhoudsindicatie (headnote) + uitspraaktekst (body)
        text_parts: List[str] = []
        inhoud = find_local("inhoudsindicatie")
        if inhoud is not None:
            t = self._element_text(inhoud)
            if t and t != "-":
                text_parts.append("=== INHOUDSINDICATIE ===\n" + t)

        body = find_local("uitspraaktekst")
        if body is not None:
            t = self._element_text(body)
            if t:
                text_parts.append("=== UITSPRAAK ===\n" + t)

        result["text"] = "\n\n".join(text_parts)
        return result

    # ── Required generators ───────────────────────────────────────────
    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all tuchtrecht decisions with extracted full text."""
        for meta in self._iter_sru_records():
            xml_bytes = self._get(meta["xml_url"])
            if not xml_bytes:
                continue
            parsed = self._parse_document(xml_bytes)
            if parsed and parsed.get("text") and len(parsed["text"]) > 150:
                raw = {**meta, **parsed}
                yield raw
            else:
                logger.debug(f"No usable text for {meta.get('ecli')}, skipping")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield decisions whose SRU 'modified' date is >= since."""
        since_date = since.strftime("%Y-%m-%d")
        for meta in self._iter_sru_records():
            modified = meta.get("modified", "")
            if modified and modified >= since_date:
                xml_bytes = self._get(meta["xml_url"])
                if not xml_bytes:
                    continue
                parsed = self._parse_document(xml_bytes)
                if parsed and parsed.get("text") and len(parsed["text"]) > 150:
                    yield {**meta, **parsed}

    def normalize(self, raw: dict) -> dict:
        """Transform a raw decision into the standard schema (with full text)."""
        ecli = raw.get("ecli", "")
        date = raw.get("uitspraakdatum") or raw.get("modified") or ""

        return {
            # Required base fields
            "_id": ecli,
            "_source": "NL/Tuchtrecht",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            # Standard fields
            "title": raw.get("title", "") or ecli,
            "text": raw.get("text", ""),  # MANDATORY FULL TEXT
            "date": date,
            "url": raw.get("public_url", f"https://tuchtrecht.overheid.nl/{ecli}"),
            # Case-law specific
            "ecli": ecli,
            "court": raw.get("court") or raw.get("creator", ""),
            "domain": raw.get("domein", ""),
            "doc_type": raw.get("doc_type", "") or raw.get("type", ""),
            "place": raw.get("plaats", ""),
            "arrondissement": raw.get("arrondissement", ""),
            "case_numbers": raw.get("zaaknummers", []),
            "subjects": raw.get("onderwerpen", []),
            "decisions": raw.get("beslissingen", []),
            "publication_date": raw.get("publicatiedatum", ""),
            "modified": raw.get("modified", ""),
            "language": "nl",
        }

    # ── Test helper ───────────────────────────────────────────────────
    def test_api(self):
        """Quick connectivity and full-text extraction test."""
        print("Testing Tuchtrecht KOOP SRU API...")
        print("\n1. Listing first SRU page...")
        first = None
        count = 0
        for meta in self._iter_sru_records():
            if first is None:
                first = meta
            count += 1
            if count >= 5:
                break
        if not first:
            print("   ERROR: No records returned")
            return
        print(f"   Got {count} records; first ECLI: {first['ecli']}")
        print(f"   XML: {first['xml_url']}")

        print("\n2. Fetching full text for first decision...")
        xml_bytes = self._get(first["xml_url"])
        if not xml_bytes:
            print("   ERROR: Could not fetch XML")
            return
        parsed = self._parse_document(xml_bytes)
        text = parsed.get("text", "")
        print(f"   Court: {parsed.get('court')}  ({parsed.get('domein')})")
        print(f"   Date: {parsed.get('uitspraakdatum')}")
        print(f"   Text length: {len(text)} characters")
        print(f"   Preview: {text[:300]}...")
        print("\nAPI test complete!")


def main():
    scraper = TuchtrechtScraper()

    if len(sys.argv) < 2:
        print(
            "Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test-api] "
            "[--sample] [--sample-size N]"
        )
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 12
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command == "test-api":
        scraper.test_api()

    elif command in ("bootstrap", "bootstrap-fast"):
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
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
        print(json.dumps(stats, indent=2, default=str))

    elif command == "update":
        stats = scraper.update()
        print(
            f"\nUpdate complete: {stats['records_new']} new, "
            f"{stats['records_updated']} updated"
        )
        print(json.dumps(stats, indent=2, default=str))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
