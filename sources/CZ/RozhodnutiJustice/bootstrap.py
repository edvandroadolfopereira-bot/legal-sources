#!/usr/bin/env python3
"""
Czech Court Decisions Open Data (rozhodnutí.justice.cz)

REST API for all Czech court decisions (district, regional, high courts).
~580K decisions from 2020 onwards with full anonymized text.

API structure:
  /api/opendata              → list of years with counts
  /api/opendata/{year}       → months
  /api/opendata/{year}/{mo}  → days
  /api/opendata/{y}/{m}/{d}  → decision list (paginated, 100/page)
  /api/finaldoc/{uuid}       → full decision with structured text

No auth required. Public open data from the Czech Ministry of Justice.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_BASE = "https://rozhodnuti.justice.cz/api"
SOURCE_ID = "CZ/RozhodnutiJustice"
RATE_LIMIT = 1.0  # seconds between requests


class RozhodnutiFetcher:
    """Fetcher for Czech court decisions from rozhodnuti.justice.cz API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "LegalDataHunter/1.0 (open-data-research)"
        })
        self._last_request = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)
        self._last_request = time.time()

    def _get_json(self, url: str) -> Any:
        self._rate_limit()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _extract_text(self, paragraphs: list) -> str:
        """Extract plain text from structured paragraph list."""
        lines = []
        for para in paragraphs:
            if not isinstance(para, dict):
                continue
            texts = para.get("texts", [])
            line_parts = []
            for t in texts:
                if isinstance(t, dict):
                    line_parts.append(t.get("text", ""))
                elif isinstance(t, str):
                    line_parts.append(t)
            line = "".join(line_parts).strip()
            if line:
                lines.append(line)
        return "\n\n".join(lines)

    def fetch_all(self, limit: Optional[int] = None, year: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Yield raw decision documents from the API."""
        count = 0

        # Get years
        years_data = self._get_json(f"{API_BASE}/opendata")
        if year:
            years_data = [y for y in years_data if y["rok"] == year]

        for year_entry in years_data:
            yr = year_entry["rok"]
            logger.info(f"Fetching year {yr} ({year_entry['pocet']} decisions)")

            # Get months
            months_data = self._get_json(f"{API_BASE}/opendata/{yr}")

            for month_entry in months_data:
                mo = month_entry["mesic"]

                # Get days
                days_data = self._get_json(f"{API_BASE}/opendata/{yr}/{mo}")

                for day_entry in days_data:
                    day_str = day_entry["datum"]  # "2026-01-05"
                    day_num = int(day_str.split("-")[2])

                    # Get decisions for this day
                    decisions = self._get_json(f"{API_BASE}/opendata/{yr}/{mo}/{day_num}")

                    items = decisions.get("items", decisions) if isinstance(decisions, dict) else decisions
                    if isinstance(items, dict):
                        items = items.get("items", [])

                    for decision in items:
                        if limit and count >= limit:
                            return

                        uuid = None
                        odkaz = decision.get("odkaz", "")
                        if "/finaldoc/" in odkaz:
                            uuid = odkaz.split("/finaldoc/")[-1]

                        if not uuid:
                            continue

                        # Fetch full document
                        try:
                            full_doc = self._get_json(f"{API_BASE}/finaldoc/{uuid}")
                        except requests.HTTPError as e:
                            logger.warning(f"Failed to fetch {uuid}: {e}")
                            continue
                        except Exception as e:
                            logger.warning(f"Error fetching {uuid}: {e}")
                            continue

                        # Merge listing metadata with full doc
                        full_doc["_listing"] = decision
                        full_doc["_uuid"] = uuid
                        count += 1
                        yield full_doc

                        if count % 10 == 0:
                            logger.info(f"Fetched {count} decisions...")

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Fetch decisions published since a given date (YYYY-MM-DD)."""
        since_dt = datetime.fromisoformat(since)
        now = datetime.now()

        for year in range(since_dt.year, now.year + 1):
            for doc in self.fetch_all(year=year):
                pub_date = doc.get("_listing", {}).get("datumZverejneni", "")
                if pub_date >= since:
                    yield doc

    def _extract_judge(self, listing: dict, metadata: dict) -> str:
        """Extract judge name from listing or metadata."""
        author = listing.get("autor", "")
        if author:
            return author
        solver = metadata.get("solver")
        if isinstance(solver, dict):
            parts = [solver.get("titlesBefore", ""),
                     solver.get("firstName", ""),
                     solver.get("lastName", ""),
                     solver.get("titlesAfter", "")]
            return " ".join(p for p in parts if p).strip()
        if isinstance(solver, str):
            return solver
        return ""

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw decision into the standard schema."""
        listing = raw.get("_listing", {})
        metadata = raw.get("metadata", {})
        uuid = raw.get("_uuid", "")

        # Extract text from structured sections
        text_parts = []

        header_text = self._extract_text(raw.get("header", []))
        if header_text:
            text_parts.append(header_text)

        verdict_text = raw.get("verdictText", "")
        if verdict_text:
            text_parts.append(verdict_text)

        justification_text = raw.get("justificationText", "")
        if justification_text:
            text_parts.append(justification_text)

        # Fallback to structured paragraph extraction
        if not justification_text:
            just_structured = self._extract_text(raw.get("justification", []))
            if just_structured:
                text_parts.append(just_structured)

        if not verdict_text:
            verdict_structured = self._extract_text(raw.get("verdict", []))
            if verdict_structured:
                text_parts.append(verdict_structured)

        full_text = "\n\n".join(text_parts)

        # Build title
        ecli = metadata.get("ecli") or listing.get("ecli", "")
        court = listing.get("soud", "") or metadata.get("courtCode", "")

        # caseNumber can be a dict like {senate, registry, index, year, pageNumber}
        case_num_raw = metadata.get("caseNumber")
        if isinstance(case_num_raw, dict):
            parts = [str(case_num_raw.get("senate", "")),
                     case_num_raw.get("registry", ""),
                     str(case_num_raw.get("index", "")),
                     str(case_num_raw.get("year", ""))]
            case_num = " ".join(p for p in parts if p).strip()
        elif isinstance(case_num_raw, str):
            case_num = case_num_raw
        else:
            case_num = listing.get("jednaciCislo", "")

        subject = metadata.get("caseSubject") or listing.get("predmetRizeni", "")

        title_parts = []
        if court:
            title_parts.append(court)
        if case_num:
            title_parts.append(case_num)
        if subject:
            title_parts.append(f"— {subject}")
        title = " ".join(title_parts) if title_parts else ecli or uuid

        # Date
        date = metadata.get("decisionAt") or listing.get("datumVydani", "")

        # Keywords
        keywords = listing.get("klicovaSlova", [])

        # Regulations cited (listing has strings, metadata has dicts)
        regulations = listing.get("zminenaUstanoveni", [])
        if not regulations:
            regs_meta = metadata.get("regulations", [])
            if isinstance(regs_meta, list):
                reg_strs = []
                for r in regs_meta:
                    if isinstance(r, str):
                        reg_strs.append(r)
                    elif isinstance(r, dict):
                        p = r.get("paragraphNumber", "")
                        n = r.get("lexNumber", "")
                        y = r.get("lexYear", "")
                        reg_strs.append(f"§ {p} č. {n}/{y}")
                regulations = reg_strs

        # Decision type (can be a list)
        decision_type_raw = metadata.get("caseResultType", "")
        if isinstance(decision_type_raw, list):
            decision_type = ", ".join(str(d) for d in decision_type_raw)
        else:
            decision_type = str(decision_type_raw) if decision_type_raw else ""

        return {
            "_id": ecli or f"CZ-{uuid}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": full_text,
            "date": date,
            "url": f"https://rozhodnuti.justice.cz/rozhodnuti/{uuid}" if uuid else "",
            "ecli": ecli,
            "case_number": case_num,
            "court": court,
            "judge": self._extract_judge(listing, metadata),
            "case_subject": subject,
            "decision_type": decision_type,
            "date_published": listing.get("datumZverejneni", ""),
            "keywords": keywords,
            "regulations_cited": regulations,
            "verdict_text": verdict_text,
        }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        fetcher = RozhodnutiFetcher()
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        logger.info("Starting bootstrap of CZ/RozhodnutiJustice...")

        sample_count = 0
        target = 15 if "--sample" in sys.argv else 50

        for raw_doc in fetcher.fetch_all(limit=target * 2):
            if sample_count >= target:
                break

            normalized = fetcher.normalize(raw_doc)
            text_len = len(normalized.get("text", ""))

            if text_len < 200:
                logger.debug(f"Skipping short decision ({text_len} chars)")
                continue

            doc_id = normalized["_id"].replace(":", "_").replace("/", "_")
            filepath = sample_dir / f"{doc_id}.json"

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)

            sample_count += 1
            logger.info(
                f"Saved [{sample_count}/{target}]: {normalized.get('case_number', doc_id)} "
                f"({text_len:,} chars) — {normalized.get('court', '?')}"
            )

        logger.info(f"Bootstrap complete. {sample_count} decisions saved to {sample_dir}")

        # Summary
        files = list(sample_dir.glob("*.json"))
        total_chars = 0
        for fp in files:
            with open(fp, encoding="utf-8") as f:
                doc = json.load(f)
            total_chars += len(doc.get("text", ""))

        logger.info(f"Summary: {len(files)} files, {total_chars:,} total text chars")
        if files:
            logger.info(f"Average: {total_chars // len(files):,} chars/decision")

    else:
        print("Usage: python bootstrap.py bootstrap [--sample]")
        print("  bootstrap         Fetch 50 sample decisions")
        print("  bootstrap --sample  Fetch 15 sample decisions")


if __name__ == "__main__":
    main()
