#!/usr/bin/env python3
"""
GN/DroitGuineen -- Droitguinéen, Guinea's Legal Reference Portal

Fetches legislation (codes, laws, decrees, OHADA acts) and court decisions
(Supreme Court, Court of Appeal, CCJA) from droitguineen.com.

Strategy:
  - Parse sitemap.xml for all /lois/ URLs (legislation + jurisprudence)
  - For each URL, fetch HTML and decode Next.js RSC payload chunks
  - Extract metadata (titre, nature, date, etc.) from RSC stream
  - Extract full text from T-tagged text blocks in the RSC stream

Usage:
  python bootstrap.py bootstrap          # Fetch all documents
  python bootstrap.py bootstrap --sample # Fetch ~15 sample records
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import logging
import time
import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.GN.DroitGuineen")

BASE_URL = "https://droitguineen.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
SOURCE_ID = "GN/DroitGuineen"


def _fetch_sitemap_urls(session: requests.Session) -> List[str]:
    """Parse sitemap.xml and return all /lois/ URLs."""
    resp = session.get(SITEMAP_URL, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for loc in root.findall(".//sm:loc", ns):
        url = loc.text.strip()
        if "/lois/" in url:
            urls.append(url)
    return urls


def _decode_rsc_payload(html: str) -> str:
    """Decode all Next.js RSC __next_f.push chunks into a single text stream."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,(.+?)\]\)</script>', html)
    all_text = ""
    for c in chunks:
        try:
            decoded = json.loads(c)
            if isinstance(decoded, str):
                all_text += decoded
        except (json.JSONDecodeError, TypeError):
            pass
    return all_text


def _extract_metadata(rsc_text: str, slug: str) -> Dict[str, Any]:
    """Extract document metadata from the RSC text stream."""
    meta = {}

    # Extract UUID (first one in a document-context pattern)
    uuid_match = re.search(
        r'\{"id":"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})","cid"',
        rsc_text,
    )
    if uuid_match:
        meta["id"] = uuid_match.group(1)
    else:
        meta["id"] = slug

    for field in [
        "titre", "titreComplet", "nature", "numero",
        "dateSignature", "datePublication", "dateEntreeVigueur",
        "etat", "sousCategorie", "signataires", "urlJO", "slug",
    ]:
        matches = re.findall(rf'"{field}":"([^"]*)"', rsc_text)
        if matches:
            meta[field] = matches[0]

    return meta


def _extract_full_text(rsc_text: str) -> str:
    """Extract full document text from T-tagged blocks in the RSC stream.

    RSC text nodes follow the pattern: <linenum>:T<hex_length>,<content>
    """
    text_blocks = re.findall(
        r'[0-9a-f]+:T[0-9a-f]+,(.*?)(?=\n[0-9a-f]+:|\Z)',
        rsc_text,
        re.DOTALL,
    )
    return "\n".join(text_blocks).strip()


def _determine_type(meta: Dict[str, Any], slug: str) -> str:
    """Determine if a document is legislation or case_law."""
    nature = (meta.get("nature") or "").upper()
    if nature in ("JURISPRUDENCE", "JURISPRUDENCE_CCJA"):
        return "case_law"
    if "jurisprudence" in slug.lower():
        return "case_law"
    return "legislation"


class DroitGuineenScraper(BaseScraper):
    """Scraper for droitguineen.com."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(str(source_dir))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (legal research; +https://legaldatahunter.com)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr,en;q=0.5",
        })

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all legislation and jurisprudence from droitguineen.com."""
        urls = _fetch_sitemap_urls(self.session)
        logger.info("Found %d /lois/ URLs in sitemap", len(urls))

        for i, url in enumerate(urls):
            try:
                yield from self._fetch_document(url, i, len(urls))
            except Exception as e:
                logger.warning("Error fetching %s: %s", url, e)
                continue
            time.sleep(1.0)

    def _fetch_document(
        self, url: str, index: int, total: int
    ) -> Generator[Dict[str, Any], None, None]:
        """Fetch a single document page and extract data."""
        slug = url.rstrip("/").split("/")[-1]
        logger.info("[%d/%d] Fetching %s", index + 1, total, slug)

        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        html = resp.text

        # Decode the RSC payload
        rsc_text = _decode_rsc_payload(html)
        if not rsc_text:
            logger.warning("Empty RSC payload for %s", slug)
            return

        # Extract metadata
        meta = _extract_metadata(rsc_text, slug)
        if not meta.get("titre") and not meta.get("titreComplet"):
            logger.warning("No title found for %s", slug)
            return

        # Extract full text
        text = _extract_full_text(rsc_text)
        if not text or len(text) < 50:
            logger.warning("Insufficient text for %s (%d chars)", slug, len(text) if text else 0)
            return

        record = {
            "id": meta.get("id", slug),
            "slug": meta.get("slug", slug),
            "title": meta.get("titre") or meta.get("titreComplet", slug),
            "title_full": meta.get("titreComplet", ""),
            "nature": meta.get("nature", ""),
            "numero": meta.get("numero", ""),
            "date_signature": meta.get("dateSignature"),
            "date_publication": meta.get("datePublication"),
            "date_entree_vigueur": meta.get("dateEntreeVigueur"),
            "etat": meta.get("etat", ""),
            "sous_categorie": meta.get("sousCategorie", ""),
            "signataires": meta.get("signataires", ""),
            "url_jo": meta.get("urlJO", ""),
            "source_url": url,
            "text": text,
        }

        yield self.normalize(record)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw record into standard schema."""
        date = raw.get("date_signature") or raw.get("date_publication")
        if date and isinstance(date, str):
            date = date[:10]

        doc_type = _determine_type(raw, raw.get("slug", ""))

        return {
            "_id": raw["id"],
            "_source": SOURCE_ID,
            "_type": doc_type,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "title_full": raw.get("title_full", ""),
            "text": raw["text"],
            "date": date,
            "url": raw["source_url"],
            "nature": raw.get("nature", ""),
            "numero": raw.get("numero", ""),
            "etat": raw.get("etat", ""),
            "sous_categorie": raw.get("sous_categorie", ""),
            "signataires": raw.get("signataires", ""),
            "url_jo": raw.get("url_jo", ""),
        }

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        """Fetch updates since a given date (not supported — full re-fetch)."""
        yield from self.fetch_all()


def _run_bootstrap(sample: bool = False):
    """Run the bootstrap process."""
    scraper = DroitGuineenScraper()
    sample_dir = Path(__file__).parent / "sample"
    sample_dir.mkdir(exist_ok=True)

    count = 0
    max_records = 15 if sample else 999999

    for record in scraper.fetch_all():
        count += 1
        text_len = len(record.get("text", ""))
        logger.info(
            "  -> [%d] %s | %s | %d chars",
            count, record["_type"], record["title"][:60], text_len,
        )

        if sample or count <= 20:
            fname = f"{record['_type']}_{count:04d}.json"
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        if count >= max_records:
            break

    logger.info("Bootstrap complete: %d records", count)
    return count


def _run_test():
    """Quick connectivity and structure test."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "LegalDataHunter/1.0 (legal research; +https://legaldatahunter.com)",
    })

    # Test 1: sitemap
    urls = _fetch_sitemap_urls(session)
    print(f"Sitemap: {len(urls)} /lois/ URLs found")

    # Test 2: fetch a legislation page
    leg_urls = [u for u in urls if "jurisprudence" not in u]
    if leg_urls:
        resp = session.get(leg_urls[0], timeout=30)
        rsc_text = _decode_rsc_payload(resp.text)
        meta = _extract_metadata(rsc_text, leg_urls[0].split("/")[-1])
        text = _extract_full_text(rsc_text)
        print(f"Legislation: '{meta.get('titre', '?')}' -- {len(text)} chars")

    # Test 3: fetch a jurisprudence page
    jur_urls = [u for u in urls if "jurisprudence" in u]
    if jur_urls:
        time.sleep(1)
        resp = session.get(jur_urls[0], timeout=30)
        rsc_text = _decode_rsc_payload(resp.text)
        meta = _extract_metadata(rsc_text, jur_urls[0].split("/")[-1])
        text = _extract_full_text(rsc_text)
        title = meta.get("titre", "?")[:60]
        print(f"Jurisprudence: '{title}' -- {len(text)} chars")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python bootstrap.py [bootstrap|test] [--sample]")
        sys.exit(1)

    cmd = args[0]
    sample = "--sample" in args

    if cmd == "test":
        _run_test()
    elif cmd == "bootstrap":
        _run_bootstrap(sample=sample)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
