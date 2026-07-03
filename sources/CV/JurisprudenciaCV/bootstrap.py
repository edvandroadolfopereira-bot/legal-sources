#!/usr/bin/env python3
"""
CV/JurisprudenciaCV - Cabo Verde Jurisprudence (CSMJ ECLI portal)

Fetches jurisprudence (acórdãos) from the official ECLI database of the
Conselho Superior da Magistratura Judicial de Cabo Verde, which aggregates
decisions from ALL Cape Verde superior courts:
  - Supremo Tribunal de Justiça
  - Tribunal da Relação de Barlavento
  - Tribunal da Relação de Sotavento

The portal exposes a clean JSON endpoint (dynatable-backed) at
`/items/loadItems`, returning each decision's ECLI, court, judge-rapporteur,
date, thematic area and the official complete headnote (`sumarioCompleto`).
Each decision additionally has a public detail page at `/juris/{ecli}/` whose
`#integral-text` tab carries the FULL decision text ("Decisão Texto Integral",
typically 6k–18k chars). The scraper fetches that full text as the document
`text`, falling back to the headnote (`sumarioCompleto`) only when a decision's
full text is not published; the headnote is always preserved in `summary`.

Data source: https://jurisprudencia.cv/
License: Public domain (official judicial decisions of the Republic of Cabo Verde)
"""

import argparse
import hashlib
import html
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.cv"
LOAD_ITEMS = BASE_URL + "/items/loadItems"
JURIS_DOC = BASE_URL + "/juris/"
SOURCE_ID = "CV/JurisprudenciaCV"

# Minimum length for a sumário to count as substantive document text.
MIN_TEXT_LEN = 100
# Minimum length for the integral text to be considered genuinely present
# (avoids treating "Não disponível." placeholders as full text).
MIN_INTEGRAL_LEN = 200

COURT_FULL = {
    "Supremo Tribunal de Justiça": "Supremo Tribunal de Justiça de Cabo Verde",
    "Tribunal da Relação de Barlavento": "Tribunal da Relação de Barlavento (Cabo Verde)",
    "Tribunal da Relação de Sotavento": "Tribunal da Relação de Sotavento (Cabo Verde)",
}


def _clean(text: str) -> str:
    """Decode HTML entities, drop tags, normalize whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('\xa0', ' ').replace('‑', '-')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    return text.strip()


def _extract_div_by_id(page: str, div_id: str) -> str:
    """Return the inner HTML of <div id="div_id">...</div>, matching nested divs."""
    m = re.search(r'<div[^>]*\bid="%s"[^>]*>' % re.escape(div_id), page)
    if not m:
        return ""
    start = m.end()
    depth = 1
    pos = start
    tag_re = re.compile(r'<(/?)div\b', re.I)
    for tm in tag_re.finditer(page, start):
        depth += -1 if tm.group(1) else 1
        if depth == 0:
            pos = tm.start()
            break
    else:
        pos = len(page)
    return page[start:pos]


def _parse_date(raw: Optional[str]) -> Optional[str]:
    """Convert DD/MM/YYYY -> ISO YYYY-MM-DD."""
    if not raw:
        return None
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw.strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except ValueError:
        return None


class JurisprudenciaCVFetcher:
    """Fetcher for the Cabo Verde CSMJ ECLI jurisprudence portal."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Legal-Data-Hunter/1.0',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
        })
        self.session.verify = False  # cert chain is incomplete on the host

    def _load_page(self, offset: int, per_page: int) -> List[Dict[str, Any]]:
        params = {"offset": offset, "perPage": per_page, "page": offset // per_page + 1}
        for attempt in range(3):
            try:
                resp = self.session.get(LOAD_ITEMS, params=params, timeout=90)
                resp.raise_for_status()
                return resp.json().get("records", [])
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"loadItems offset={offset} attempt {attempt+1} failed: {e}")
                time.sleep(2.0 * (attempt + 1))
        return []

    def _fetch_full_text(self, ecli: str) -> str:
        """Fetch the full 'Decisão Texto Integral' from the /juris/{ecli}/ page."""
        if not ecli:
            return ""
        url = f"{JURIS_DOC}{ecli}/"
        for attempt in range(3):
            try:
                resp = self.session.get(
                    url, timeout=90,
                    headers={'Accept': 'text/html,application/xhtml+xml',
                             'X-Requested-With': ''},
                )
                resp.raise_for_status()
                inner = _extract_div_by_id(resp.text, "integral-text")
                text = _clean(inner)
                # The tab pane is prefixed with the heading "Decisão Texto Integral".
                text = re.sub(r'^Decis[aã]o Texto Integral\s*', '', text).strip()
                if text.lower().startswith("não disponível") or text.lower().startswith("nao disponivel"):
                    return ""
                return text if len(text) >= MIN_INTEGRAL_LEN else ""
            except requests.RequestException as e:
                logger.warning(f"full-text {ecli} attempt {attempt+1} failed: {e}")
                time.sleep(2.0 * (attempt + 1))
        return ""

    def _iter_raw(self, per_page: int = 250) -> Iterator[Dict[str, Any]]:
        """Page through the whole collection."""
        offset = 0
        while True:
            records = self._load_page(offset, per_page)
            if not records:
                break
            for r in records:
                yield r
            if len(records) < per_page:
                break
            offset += per_page
            time.sleep(1.0)

    def normalize(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform a raw loadItems record into the standard schema."""
        summary = _clean(raw.get("sumarioCompleto") or raw.get("sumario") or "")
        if len(summary) < MIN_TEXT_LEN:
            return None  # metadata-only record, no substantive headnote

        ecli = (raw.get("ecli") or "").strip()
        # Prefer the full "Decisão Texto Integral"; fall back to the headnote.
        full_text = self._fetch_full_text(ecli)
        text = full_text if full_text else summary
        time.sleep(0.5)  # be polite between detail-page fetches
        court = (raw.get("tribunal") or "").strip()
        date = _parse_date(raw.get("dataAcordao"))
        year = None
        if date:
            year = int(date[:4])
        elif ecli:
            ym = re.search(r':(\d{4}):', ecli)
            if ym:
                year = int(ym.group(1))

        tematica = _clean(raw.get("tematica") or "")
        relator = _clean(raw.get("relator") or "")
        if relator.upper() in ("N/D", "ND", ""):
            relator = None

        if ecli:
            doc_id = ecli.replace(":", "-")
            url = f"{JURIS_DOC}{ecli}/"
        else:
            doc_id = "h" + hashlib.sha256(summary.encode()).hexdigest()[:14]
            url = f"{BASE_URL}/juris"

        title_bits = [court or "Decisão"]
        if ecli:
            title_bits.append(ecli)
        if tematica:
            title_bits.append(tematica.split('|')[0].strip())
        title = " — ".join(b for b in title_bits if b)

        return {
            "_id": f"CV-JURIS-{doc_id}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title[:300],
            "text": text,
            "summary": summary,
            "has_full_text": bool(full_text),
            "date": date,
            "url": url,
            "ecli": ecli or None,
            "court": COURT_FULL.get(court, court) or None,
            "rapporteur": relator,
            "thematic_area": tematica or None,
            "decision": (_clean(raw.get("decisao") or "") or None),
            "year": year,
            "country": "CV",
            "language": "pt",
        }

    def fetch_all(self) -> Iterator[Dict[str, Any]]:
        seen = set()
        for raw in self._iter_raw():
            record = self.normalize(raw)
            if not record or record["_id"] in seen:
                continue
            seen.add(record["_id"])
            yield record

    def fetch_sample(self, max_records: int = 15) -> Iterator[Dict[str, Any]]:
        count = 0
        for record in self.fetch_all():
            if count >= max_records:
                return
            count += 1
            logger.info(f"  Sample {count}/{max_records}: {record['title'][:55]} "
                        f"({len(record['text'])} chars)")
            yield record

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        for record in self.fetch_all():
            if not since or (record.get("date") and record["date"] >= since):
                yield record


def _save_sample(records: Iterator[Dict[str, Any]], sample_dir: Path) -> int:
    sample_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in records:
        safe_id = record["_id"].replace("/", "_")
        with open(sample_dir / f"{safe_id}.json", "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        count += 1
    logger.info(f"Bootstrap complete: {count} sample records saved to {sample_dir}")
    return count


def _save_full(records: Iterator[Dict[str, Any]], data_dir: Path) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = data_dir / "records.jsonl"
    count = 0
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if count % 50 == 0:
                logger.info(f"Progress: {count} records written")
    logger.info(f"Full bootstrap complete: {count} records -> {jsonl_path}")
    return count


def main():
    parser = argparse.ArgumentParser(description="CV/JurisprudenciaCV Fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "updates"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Sample mode (15 records)")
    parser.add_argument("--full", action="store_true", help="Full bootstrap")
    parser.add_argument("--since", help="ISO date for updates mode")
    args = parser.parse_args()

    fetcher = JurisprudenciaCVFetcher()
    base = Path(__file__).parent

    if args.command == "updates":
        for record in fetcher.fetch_updates(args.since or ""):
            print(json.dumps(record, ensure_ascii=False))
        return

    if args.sample or not args.full:
        _save_sample(fetcher.fetch_sample(max_records=15), base / "sample")
    else:
        _save_full(fetcher.fetch_all(), base / "data")


if __name__ == "__main__":
    main()
