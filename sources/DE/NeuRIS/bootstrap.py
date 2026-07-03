#!/usr/bin/env python3
"""
NEURIS — German Federal Legal Information System

REST API at https://testphase.rechtsinformationen.bund.de/v1
No authentication required. Covers federal case law and legislation.

Data is public domain (amtliche Werke) under German law (§ 5 UrhG).
"""

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "https://testphase.rechtsinformationen.bund.de/v1"
SOURCE_ID = "DE/NeuRIS"
PAGE_SIZE = 100
MAX_RETRIES = 3
DELAY = 0.5


class NEURISFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "application/json",
        })

    def _get(self, url: str, params: dict = None) -> Optional[dict]:
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=60)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        return None

    def _get_text(self, url: str) -> Optional[str]:
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=60, headers={"Accept": "text/html"})
                if resp.status_code == 404:
                    return None  # No retries for 404
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if "404" in str(e):
                    return None
                logger.warning(f"Text request failed (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        return None

    @staticmethod
    def _strip_html(html_str: str) -> str:
        if not html_str:
            return ""
        text = re.sub(r"<[^>]+>", " ", html_str)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        text = re.sub(r"&#\d+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ── Case Law ──────────────────────────────────────────────────────

    def _assemble_case_text(self, detail: dict) -> str:
        parts = []
        for field in ("guidingPrinciple", "headline", "headnote", "otherHeadnote",
                       "tenor", "caseFacts", "decisionGrounds", "grounds",
                       "otherLongText", "dissentingOpinion"):
            val = detail.get(field)
            if val and val.strip():
                parts.append(val.strip())
        return "\n\n".join(parts)

    def normalize_case_law(self, detail: dict) -> Dict[str, Any]:
        doc_num = detail.get("documentNumber", "")
        text = self._assemble_case_text(detail)
        file_nums = detail.get("fileNumbers") or []
        return {
            "_id": detail.get("ecli") or doc_num,
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": detail.get("headline") or detail.get("guidingPrinciple") or f"{detail.get('courtName', '')} {', '.join(file_nums)}",
            "text": text,
            "date": detail.get("decisionDate"),
            "url": f"https://testphase.rechtsinformationen.bund.de/suche/{doc_num}",
            "documentNumber": doc_num,
            "ecli": detail.get("ecli"),
            "fileNumbers": file_nums,
            "courtName": detail.get("courtName"),
            "courtType": detail.get("courtType"),
            "documentType": detail.get("documentType"),
            "judicialBody": detail.get("judicialBody"),
            "location": detail.get("location"),
            "keywords": detail.get("keywords") or [],
            "language": detail.get("inLanguage", "de"),
        }

    def fetch_case_law(self, limit: int = 0) -> Iterator[Dict[str, Any]]:
        page = 0
        total_yielded = 0
        while True:
            data = self._get(f"{API_BASE}/case-law", params={
                "size": PAGE_SIZE, "pageIndex": page, "sort": "-date"
            })
            if not data:
                break
            members = data.get("member", [])
            if not members:
                break
            for member in members:
                item = member.get("item", {})
                doc_num = item.get("documentNumber")
                if not doc_num:
                    continue
                detail = self._get(f"{API_BASE}/case-law/{doc_num}")
                if not detail:
                    continue
                rec = self.normalize_case_law(detail)
                if rec.get("text"):
                    yield rec
                    total_yielded += 1
                    if limit and total_yielded >= limit:
                        return
                else:
                    logger.warning(f"No text for case {doc_num}, trying HTML")
                    html_text = self._get_text(f"{API_BASE}/case-law/{doc_num}.html")
                    if html_text:
                        rec["text"] = self._strip_html(html_text)
                        if rec["text"]:
                            yield rec
                            total_yielded += 1
                            if limit and total_yielded >= limit:
                                return
                time.sleep(DELAY)
            total = data.get("totalItems", 0)
            logger.info(f"Case law page {page}: {total_yielded} yielded so far (total available: {total})")
            view = data.get("view", {})
            if not view.get("next"):
                break
            page += 1

    # ── Legislation ───────────────────────────────────────────────────

    def normalize_legislation(self, item: dict, full_text: str) -> Dict[str, Any]:
        work = item.get("exampleOfWork", {})
        eli = item.get("legislationIdentifier", "")
        return {
            "_id": eli or item.get("@id", ""),
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": item.get("name") or item.get("alternateName") or eli,
            "text": full_text,
            "date": work.get("legislationDate") or work.get("datePublished"),
            "url": f"https://testphase.rechtsinformationen.bund.de/suche/{eli}",
            "eli": eli,
            "abbreviation": item.get("abbreviation"),
            "alternateName": item.get("alternateName"),
            "legislationLegalForce": item.get("legislationLegalForce"),
            "temporalCoverage": item.get("temporalCoverage"),
            "publicationIssue": work.get("isPartOf", {}).get("name"),
            "language": item.get("inLanguage", "de") if isinstance(item.get("inLanguage"), str) else "de",
        }

    def fetch_legislation(self, limit: int = 0) -> Iterator[Dict[str, Any]]:
        page = 0
        total_yielded = 0
        while True:
            data = self._get(f"{API_BASE}/legislation", params={
                "size": PAGE_SIZE, "pageIndex": page, "sort": "-date"
            })
            if not data:
                break
            members = data.get("member", [])
            if not members:
                break
            for member in members:
                item = member.get("item", {})
                encodings = item.get("encoding", [])
                html_url = None
                for enc in encodings:
                    if enc.get("encodingFormat") == "text/html":
                        html_url = enc.get("contentUrl")
                        break
                if not html_url:
                    continue
                if html_url.startswith("/"):
                    full_url = f"https://testphase.rechtsinformationen.bund.de{html_url}"
                elif html_url.startswith("http"):
                    full_url = html_url
                else:
                    full_url = f"{API_BASE}/legislation/{html_url}"
                html_text = self._get_text(full_url)
                if not html_text:
                    continue
                clean = self._strip_html(html_text)
                if not clean or len(clean) < 50:
                    logger.warning(f"Insufficient text for {item.get('legislationIdentifier')}")
                    continue
                rec = self.normalize_legislation(item, clean)
                yield rec
                total_yielded += 1
                if limit and total_yielded >= limit:
                    return
                time.sleep(DELAY)
            total = data.get("totalItems", 0)
            logger.info(f"Legislation page {page}: {total_yielded} yielded so far (total available: {total})")
            view = data.get("view", {})
            if not view.get("next"):
                break
            page += 1

    # ── Combined ──────────────────────────────────────────────────────

    def fetch_all(self, limit: int = 0) -> Iterator[Dict[str, Any]]:
        yield from self.fetch_case_law(limit=limit)
        yield from self.fetch_legislation(limit=limit)

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        for rec in self.fetch_case_law():
            if rec.get("date") and rec["date"] >= since:
                yield rec
            else:
                break
        for rec in self.fetch_legislation():
            if rec.get("date") and rec["date"] >= since:
                yield rec
            else:
                break


def bootstrap(sample: bool = False):
    fetcher = NEURISFetcher()
    base = Path(__file__).parent
    count = 0

    if sample:
        sample_dir = base / "sample"
        sample_dir.mkdir(exist_ok=True)
        for rec in fetcher.fetch_all(limit=12):
            count += 1
            path = sample_dir / f"{count:04d}.json"
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Sample {count}: {rec['_type']} | {rec['title'][:60]}... | text={len(rec.get('text',''))} chars")
    else:
        data_dir = base / "data"
        data_dir.mkdir(exist_ok=True)
        out_path = data_dir / "records.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in fetcher.fetch_all(limit=0):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
        logger.info(f"Wrote {count} records to {out_path}")

    logger.info(f"Done. Total records: {count}")
    return count


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DE/NeuRIS bootstrap (REST API)")
    parser.add_argument("command", nargs="?", default="bootstrap",
                        choices=["bootstrap", "bootstrap-fast"], help="Command to run")
    parser.add_argument("--sample", action="store_true", help="Fetch sample data only")
    parser.add_argument("--full", action="store_true", help="Full pull (default for non-sample)")
    args, _unknown = parser.parse_known_args()

    n = bootstrap(sample=args.sample)
    if args.sample and n < 10:
        logger.error(f"Only {n} samples (need 10+). Check the NeuRIS API.")
        sys.exit(1)


if __name__ == "__main__":
    main()
