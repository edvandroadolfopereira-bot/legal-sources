#!/usr/bin/env python3
"""
INTL/BCEAO-Regulations -- Banque Centrale des États de l'Afrique de l'Ouest

Banking, monetary, payment-systems, microfinance (SFD), external-financial-
relations and AML/CFT regulations issued by the BCEAO for the 8 UEMOA member
states (Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger,
Sénégal, Togo).

Strategy:
  1. Enumerate the six "réglementations" category listing pages on bceao.int.
     These pages are server-rendered Drupal Views (paginated via ?page=N) and
     link to individual regulation node aliases.
  2. For each node, fetch `<alias>?_format=json` — the Drupal node REST export —
     which gives the title, date, document type and the attached PDF
     (field_fichier.url).
  3. Download the PDF and extract full text via the shared pdf_extract backend
     (pdfplumber / pypdf / fitz fallback).

Usage:
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap --full
  python bootstrap.py test
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.INTL.BCEAO-Regulations")

HOST = "https://www.bceao.int"
DELAY = 2.0
SOURCE_ID = "INTL/BCEAO-Regulations"

# The six regulatory category listing pages (Drupal Views, paginated).
CATEGORIES = {
    "/fr/reglementations/textes-regissant-la-politique-monetaire": "Politique monétaire",
    "/fr/reglementations/reglementation-bancaire": "Réglementation bancaire",
    "/fr/reglementations/reglementation-des-systemes-de-paiement": "Systèmes de paiement",
    "/fr/reglementations/reglementation-des-systemes-financiers-decentralises": "Systèmes financiers décentralisés (microfinance)",
    "/fr/reglementations/reglementation-des-relations-financieres-exterieures": "Relations financières extérieures",
    "/fr/reglementations/lutte-contre-le-blanchiment-de-capitaux-et-le-financement-du-terrorisme": "Lutte contre le blanchiment (LBC/FT)",
}
CATEGORY_SLUGS = set(CATEGORIES.keys())

# UEMOA member states covered by BCEAO regulations.
UEMOA_STATES = ["BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"]

UA = {"User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0; +legal-data-hunter)"}

DOC_HREF_RE = re.compile(r'href="(/fr/reglementations/[a-z0-9][a-z0-9\-]{6,})\s*"')


def _get(url: str, *, as_json: bool = False, retries: int = 3):
    """HTTP GET with retries. Returns text, or parsed JSON, or None."""
    for attempt in range(retries):
        try:
            time.sleep(DELAY)
            r = requests.get(url, headers=UA, timeout=45, verify=False)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            logger.warning("GET %s -> HTTP %d (attempt %d)", url, r.status_code, attempt + 1)
        except Exception as e:
            logger.warning("GET %s failed: %s (attempt %d)", url, e, attempt + 1)
        if attempt < retries - 1:
            time.sleep(3)
    return None


def _enumerate_category(cat_slug: str) -> Generator[str, None, None]:
    """Yield individual regulation node slugs for one category, page by page."""
    seen: set = set()
    for page in range(0, 80):
        url = f"{HOST}{cat_slug}?page={page}"
        html = _get(url)
        if not html:
            break
        slugs = [s for s in DOC_HREF_RE.findall(html)
                 if s.count("/") == 3 and s not in CATEGORY_SLUGS]
        new = [s for s in dict.fromkeys(slugs) if s not in seen]
        if not new:
            break
        for s in new:
            seen.add(s)
            yield s


def _classify(doc_type: str, title: str) -> str:
    """Map a BCEAO document to a project _type."""
    t = (title or "").lower()
    if t.startswith("note d") or "note d'information" in t or t.startswith("guide"):
        return "doctrine"
    # Instructions, avis, décisions, circulaires, lois, règlements, conventions.
    return "legislation"


def _node_json(slug: str) -> Optional[Dict[str, Any]]:
    data = _get(f"{HOST}{slug}?_format=json", as_json=True)
    if not isinstance(data, dict) or "nid" not in data:
        return None
    return data


def _field_value(node: Dict[str, Any], field: str, key: str = "value"):
    v = node.get(field)
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v[0].get(key)
    return None


class BCEAORegulationsScraper(BaseScraper):
    """Scraper for INTL/BCEAO-Regulations."""

    def __init__(self):
        super().__init__(str(Path(__file__).parent))

    def _iter_slugs(self) -> Generator[tuple, None, None]:
        for cat_slug, cat_label in CATEGORIES.items():
            logger.info("Enumerating category: %s", cat_label)
            for slug in _enumerate_category(cat_slug):
                yield slug, cat_label

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        seen_nids: set = set()
        count = 0
        for slug, cat_label in self._iter_slugs():
            node = _node_json(slug)
            if not node:
                logger.warning("No node JSON for %s", slug)
                continue

            nid = _field_value(node, "nid")
            if nid in seen_nids:
                continue
            seen_nids.add(nid)

            title = (_field_value(node, "title") or "").strip()
            doc_type = _field_value(node, "type", "target_id") or ""
            pdf_url = None
            ff = node.get("field_fichier")
            if isinstance(ff, list) and ff and isinstance(ff[0], dict):
                pdf_url = ff[0].get("url")
            if pdf_url and pdf_url.startswith("/"):
                pdf_url = urljoin(HOST, pdf_url)

            date = _field_value(node, "field_date")

            if not pdf_url:
                logger.info("No PDF attached, skipping: %s", title[:60])
                continue

            doc_id = f"INTL_BCEAO_{nid}"
            logger.info("PDF [%d]: %s", count + 1, title[:70])
            try:
                text = extract_pdf_markdown(
                    source=SOURCE_ID,
                    source_id=doc_id,
                    pdf_url=pdf_url,
                    table="legislation",
                )
            except Exception as e:
                logger.warning("PDF extraction failed for %s: %s", pdf_url, e)
                continue

            if not text or len(text.strip()) < 100:
                logger.warning("Insufficient text (%d chars): %s",
                               len(text or ""), title[:50])
                continue

            count += 1
            yield {
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "date": date,
                "url": f"{HOST}{slug}",
                "pdf_url": pdf_url,
                "category": cat_label,
                "_type": _classify(doc_type, title),
            }

        logger.info("Completed: %d documents fetched", count)

    def fetch_updates(self, since: str = None) -> Generator[Dict[str, Any], None, None]:
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_id": raw["doc_id"],
            "_source": SOURCE_ID,
            "_type": raw.get("_type", "legislation"),
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "url": raw.get("url", ""),
            "pdf_url": raw.get("pdf_url", ""),
            "category": raw.get("category", ""),
            "jurisdiction": "UEMOA",
            "countries": UEMOA_STATES,
        }

    def test(self) -> bool:
        logger.info("Testing BCEAO category enumeration + node JSON...")
        cat = "/fr/reglementations/reglementation-bancaire"
        slugs = list(_enumerate_category(cat))
        logger.info("reglementation-bancaire: %d node slugs", len(slugs))
        if not slugs:
            logger.error("No node slugs enumerated")
            return False
        node = _node_json(slugs[0])
        if not node:
            logger.error("Node JSON fetch failed for %s", slugs[0])
            return False
        ff = node.get("field_fichier")
        pdf = ff[0].get("url") if isinstance(ff, list) and ff else None
        logger.info("First node title: %s | PDF: %s",
                    (_field_value(node, "title") or "")[:60], bool(pdf))
        return bool(pdf)


def main():
    parser = argparse.ArgumentParser(description="INTL/BCEAO-Regulations data fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "update", "test"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    scraper = BCEAORegulationsScraper()

    if args.command == "test":
        sys.exit(0 if scraper.test() else 1)
    elif args.command in ("bootstrap", "bootstrap-fast"):
        scraper.bootstrap(sample_mode=args.sample, sample_size=15)
    elif args.command == "update":
        scraper.bootstrap(sample_mode=False)


if __name__ == "__main__":
    main()
