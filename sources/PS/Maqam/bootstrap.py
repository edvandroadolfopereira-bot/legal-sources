#!/usr/bin/env python3
"""
PS/Maqam - Palestine Laws Encyclopedia (Maqam, An-Najah University)

Fetches legislation and court judgments from https://maqam.najah.edu.
Scrapes listing pages for IDs, then fetches detail pages for metadata and full text.

~2,080 laws and ~11,080 court judgments from Palestinian courts and legislature.
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pypdf
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://maqam.najah.edu"
SOURCE_ID = "PS/Maqam"
SAMPLE_DIR = Path(__file__).parent / "sample"

MIN_TEXT_LENGTH = 200


class MaqamFetcher:
    """Fetcher for Maqam Palestine legislation and court judgments."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar,en;q=0.5",
        })

    def _clean_html(self, text: str) -> str:
        """Strip HTML tags and clean whitespace."""
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = text.replace("\xa0", " ")
        text = re.sub(r"[\u200e\u200f]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_pdf_url(self, html: str) -> Optional[str]:
        """Find PDF attachment URL in the page."""
        m = re.search(r'href="(/media/uploads/[^"]+\.(?:pdf|rtf))"', html, re.I)
        if m:
            return BASE_URL + m.group(1)
        return None

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download and extract text from a PDF."""
        if not pdf_url.lower().endswith(".pdf"):
            return ""
        try:
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()
            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            return "\n".join(pages_text).strip()
        except Exception as e:
            logger.warning("PDF extraction failed for %s: %s", pdf_url, e)
            return ""

    # ── Legislation ──────────────────────────────────────────────────

    def get_legislation_ids_from_listing(self, max_pages: int = 5) -> List[int]:
        """Get legislation IDs from listing pages."""
        ids = []
        for page in range(1, max_pages + 1):
            try:
                url = f"{BASE_URL}/legislation/?page={page}"
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                found = re.findall(r"/legislation/(\d+)/", resp.text)
                ids.extend(int(x) for x in found)
                logger.info("Legislation listing page %d: found %d items", page, len(found))
                if not found:
                    break
            except Exception as e:
                logger.warning("Failed legislation listing page %d: %s", page, e)
                break
            time.sleep(1)
        return sorted(set(ids), reverse=True)

    def _extract_legislation_metadata(self, html: str) -> Dict[str, Optional[str]]:
        """Extract metadata fields from legislation detail page."""
        meta: Dict[str, Optional[str]] = {}

        # Title from <title> tag
        title_m = re.search(r"<title>(.*?)</title>", html, re.S)
        if title_m:
            meta["title"] = self._clean_html(title_m.group(1))

        field_map = {
            "السنة": "year",
            "الرقم": "number",
            "نوع التشريع": "legislation_type",
            "نوع تشريع - فرعي": "legislation_subtype",
            "التصينف الموضوعي": "subject",
            "تصنيف موضوعي - فرعي": "subject_sub",
            "حالة التشريع": "status",
        }

        for ar_label, key in field_map.items():
            pattern = re.escape(ar_label) + r"\s*</dt>\s*<dd[^>]*>\s*(.*?)\s*</dd>"
            m = re.search(pattern, html, re.S)
            if m:
                val = self._clean_html(m.group(1))
                if val:
                    meta[key] = val

        return meta

    def _extract_legislation_text(self, html: str) -> str:
        """Extract full text of legislation (all articles combined)."""
        # Find all article text blocks in <dd class="col-md-9"> after المادة
        # The articles are inside <dl class="row"> blocks after the metadata card
        articles = []

        # Get the second card-body (articles section) onward
        parts = html.split('<div class="card-body">')
        if len(parts) < 3:
            # Fallback: try to extract all <dd> content after the metadata
            pass

        article_html = '<div class="card-body">'.join(parts[2:]) if len(parts) >= 3 else html

        # Extract article headings and content
        # Pattern: المادة (N) followed by <dd> content
        article_pattern = re.compile(
            r'المادة\s*\((\d+)\)\s*</a>.*?<dd class="col-md-9">\s*(.*?)\s*</dd>',
            re.S
        )
        for m in article_pattern.finditer(article_html):
            num = m.group(1)
            content = self._clean_html(m.group(2))
            if content:
                articles.append(f"المادة ({num}): {content}")

        if articles:
            return "\n\n".join(articles)

        # Fallback: extract all <p> tags from article section
        if len(parts) >= 3:
            text = self._clean_html(article_html)
            if len(text) >= MIN_TEXT_LENGTH:
                return text

        return ""

    def _extract_legislation_sections(self, html: str) -> List[str]:
        """Extract chapter/section headings."""
        sections = []
        for m in re.finditer(r'<h[56] class="text-center">\s*(.*?)\s*</h[56]>', html, re.S):
            section = self._clean_html(m.group(1))
            if section:
                sections.append(section)
        return sections

    def fetch_legislation(self, leg_id: int) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single legislation item."""
        url = f"{BASE_URL}/legislation/{leg_id}/"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch legislation %d: %s", leg_id, e)
            return None

        html = resp.text
        meta = self._extract_legislation_metadata(html)
        text = self._extract_legislation_text(html)
        sections = self._extract_legislation_sections(html)

        # Fallback to PDF if HTML text is too short
        if len(text) < MIN_TEXT_LENGTH:
            pdf_url = self._extract_pdf_url(html)
            if pdf_url:
                logger.info("Short HTML text (%d chars) for legislation %d, trying PDF...", len(text), leg_id)
                pdf_text = self._extract_pdf_text(pdf_url)
                if pdf_text and len(pdf_text) >= MIN_TEXT_LENGTH:
                    text = pdf_text

        return {
            "id": leg_id,
            "url": url,
            "title": meta.get("title", ""),
            "year": meta.get("year"),
            "number": meta.get("number"),
            "legislation_type": meta.get("legislation_type"),
            "legislation_subtype": meta.get("legislation_subtype"),
            "subject": meta.get("subject"),
            "subject_sub": meta.get("subject_sub"),
            "status": meta.get("status"),
            "sections": sections,
            "text": text,
        }

    def normalize_legislation(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw legislation into standard schema."""
        year = raw.get("year")
        date = f"{year}-01-01" if year and re.match(r"^\d{4}$", str(year)) else None

        return {
            "_id": f"PS-Maqam-L{raw['id']}",
            "_source": SOURCE_ID,
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": date,
            "url": raw.get("url", ""),
            "year": raw.get("year"),
            "number": raw.get("number"),
            "legislation_type": raw.get("legislation_type"),
            "legislation_subtype": raw.get("legislation_subtype"),
            "subject": raw.get("subject"),
            "enforcement_status": raw.get("status"),
            "language": "ar",
        }

    # ── Judgments ─────────────────────────────────────────────────────

    def get_judgment_ids_from_listing(self, max_pages: int = 5) -> List[int]:
        """Get judgment IDs from listing pages."""
        ids = []
        for page in range(1, max_pages + 1):
            try:
                url = f"{BASE_URL}/judgments/?page={page}"
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                found = re.findall(r"/judgments/(\d+)/", resp.text)
                ids.extend(int(x) for x in found)
                logger.info("Judgment listing page %d: found %d items", page, len(found))
                if not found:
                    break
            except Exception as e:
                logger.warning("Failed judgment listing page %d: %s", page, e)
                break
            time.sleep(1)
        return sorted(set(ids), reverse=True)

    def _extract_judgment_metadata(self, html: str) -> Dict[str, Optional[str]]:
        """Extract metadata from judgment detail page."""
        meta: Dict[str, Optional[str]] = {}

        # Title from <title>
        title_m = re.search(r"<title>(.*?)</title>", html, re.S)
        if title_m:
            raw_title = self._clean_html(title_m.group(1))
            meta["title"] = raw_title
            # Parse structured title: القضية رقم NUMBER/YEAR المنعقدة في COURT بتاريخ DATE
            m = re.search(
                r"القضية رقم\s*(\d+)\s*/\s*(\d+)\s*المنعقدة في\s*(.*?)\s*بتاريخ\s*(\d{4}-\d{2}-\d{2})",
                raw_title
            )
            if m:
                meta["case_number"] = m.group(1)
                meta["case_year"] = m.group(2)
                meta["court"] = m.group(3).strip()
                meta["date"] = m.group(4)

        field_map = {
            "السنة": "year",
            "الرقم": "number",
            "تاريخ الفصل": "decision_date",
            "المحكمة": "court_name",
            "نوع التقاضي": "case_type",
        }

        for ar_label, key in field_map.items():
            pattern = re.escape(ar_label) + r"\s*</dt>\s*<dd[^>]*>\s*(.*?)\s*</dd>"
            m = re.search(pattern, html, re.S)
            if m:
                val = self._clean_html(m.group(1))
                if val:
                    meta[key] = val

        return meta

    def _extract_judgment_text(self, html: str) -> str:
        """Extract judgment full text."""
        # Text is after <h4 class="card-title text-center">النص</h4>
        m = re.search(r'النص\s*</h4>\s*(.*?)(?:</div>\s*</div>|<footer)', html, re.S)
        if m:
            text = self._clean_html(m.group(1))
            if len(text) >= MIN_TEXT_LENGTH:
                return text

        # Broader fallback
        parts = html.split('<div class="card-body">')
        if len(parts) >= 3:
            text = self._clean_html(parts[2].split("</div>")[0])
            if len(text) >= MIN_TEXT_LENGTH:
                return text

        return ""

    def fetch_judgment(self, jid: int) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single judgment."""
        url = f"{BASE_URL}/judgments/{jid}/"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch judgment %d: %s", jid, e)
            return None

        html = resp.text
        meta = self._extract_judgment_metadata(html)
        text = self._extract_judgment_text(html)

        return {
            "id": jid,
            "url": url,
            "title": meta.get("title", ""),
            "case_number": meta.get("case_number") or meta.get("number"),
            "case_year": meta.get("case_year") or meta.get("year"),
            "court": meta.get("court") or meta.get("court_name"),
            "date": meta.get("date") or meta.get("decision_date"),
            "case_type": meta.get("case_type"),
            "text": text,
        }

    def normalize_judgment(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw judgment into standard schema."""
        date = raw.get("date")
        if date and not re.match(r"\d{4}-\d{2}-\d{2}", date):
            date = None

        return {
            "_id": f"PS-Maqam-J{raw['id']}",
            "_source": SOURCE_ID,
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": date,
            "url": raw.get("url", ""),
            "court": raw.get("court"),
            "case_number": raw.get("case_number"),
            "case_year": raw.get("case_year"),
            "case_type": raw.get("case_type"),
            "language": "ar",
        }

    # ── Combined fetch ────────────────────────────────────────────────

    def fetch_all(self) -> Iterator[Dict[str, Any]]:
        """Yield all legislation and judgments."""
        # Legislation
        leg_ids = self.get_legislation_ids_from_listing(max_pages=104)
        logger.info("Total legislation IDs: %d", len(leg_ids))
        for i, lid in enumerate(leg_ids):
            raw = self.fetch_legislation(lid)
            if raw and raw.get("text"):
                yield self.normalize_legislation(raw)
            if (i + 1) % 50 == 0:
                logger.info("Legislation progress: %d/%d", i + 1, len(leg_ids))
            time.sleep(1.5)

        # Judgments
        j_ids = self.get_judgment_ids_from_listing(max_pages=554)
        logger.info("Total judgment IDs: %d", len(j_ids))
        for i, jid in enumerate(j_ids):
            raw = self.fetch_judgment(jid)
            if raw and raw.get("text"):
                yield self.normalize_judgment(raw)
            if (i + 1) % 50 == 0:
                logger.info("Judgment progress: %d/%d", i + 1, len(j_ids))
            time.sleep(1.5)

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield documents modified since a date."""
        since_date = datetime.fromisoformat(since).date()

        # Check newest legislation
        leg_ids = self.get_legislation_ids_from_listing(max_pages=5)
        for lid in leg_ids:
            raw = self.fetch_legislation(lid)
            if not raw or not raw.get("text"):
                continue
            yield self.normalize_legislation(raw)
            time.sleep(1.5)

        # Check newest judgments
        j_ids = self.get_judgment_ids_from_listing(max_pages=10)
        for jid in j_ids:
            raw = self.fetch_judgment(jid)
            if not raw or not raw.get("text"):
                continue
            rec = self.normalize_judgment(raw)
            if rec.get("date"):
                try:
                    if datetime.fromisoformat(rec["date"]).date() < since_date:
                        break
                except ValueError:
                    pass
            yield rec
            time.sleep(1.5)


def bootstrap_sample():
    """Fetch sample data for validation."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = MaqamFetcher()

    # Clear old samples
    for f in SAMPLE_DIR.glob("*.json"):
        f.unlink()

    count = 0

    # Legislation samples (5 items from first 2 pages)
    leg_ids = fetcher.get_legislation_ids_from_listing(max_pages=2)
    logger.info("Found %d legislation IDs", len(leg_ids))
    for lid in leg_ids[:8]:
        raw = fetcher.fetch_legislation(lid)
        if not raw:
            continue
        rec = fetcher.normalize_legislation(raw)
        if not rec.get("text"):
            logger.warning("No text for legislation %d, skipping", lid)
            continue
        outfile = SAMPLE_DIR / f"{rec['_id']}.json"
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        logger.info("Saved %s — %d chars, type=%s, year=%s",
                     rec["_id"], len(rec["text"]), rec["_type"], rec.get("year", "?"))
        count += 1
        if count >= 5:
            break
        time.sleep(1.5)

    # Judgment samples (10 items from first 3 pages)
    j_ids = fetcher.get_judgment_ids_from_listing(max_pages=3)
    logger.info("Found %d judgment IDs", len(j_ids))
    j_count = 0
    for jid in j_ids:
        if j_count >= 10:
            break
        raw = fetcher.fetch_judgment(jid)
        if not raw:
            continue
        rec = fetcher.normalize_judgment(raw)
        if not rec.get("text"):
            logger.warning("No text for judgment %d, skipping", jid)
            continue
        outfile = SAMPLE_DIR / f"{rec['_id']}.json"
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        logger.info("Saved %s — %d chars, court=%s, date=%s",
                     rec["_id"], len(rec["text"]), rec.get("court", "?"), rec.get("date", "?"))
        count += 1
        j_count += 1
        time.sleep(1.5)

    logger.info("Sample complete: %d records saved to %s", count, SAMPLE_DIR)
    return count


def main():
    parser = argparse.ArgumentParser(description="PS/Maqam Palestine Laws & Court Judgments")
    parser.add_argument("command", choices=["bootstrap", "fetch_all", "fetch_updates"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample data only")
    parser.add_argument("--since", type=str, help="Fetch updates since date (ISO 8601)")
    args = parser.parse_args()

    if args.command == "bootstrap":
        if args.sample:
            count = bootstrap_sample()
            if count < 10:
                logger.error("Only %d samples collected, need at least 10", count)
                sys.exit(1)
        else:
            fetcher = MaqamFetcher()
            count = 0
            for record in fetcher.fetch_all():
                count += 1
            logger.info("Full bootstrap complete: %d records", count)
    elif args.command == "fetch_updates":
        if not args.since:
            logger.error("--since required for fetch_updates")
            sys.exit(1)
        fetcher = MaqamFetcher()
        for record in fetcher.fetch_updates(args.since):
            print(json.dumps(record, ensure_ascii=False))
    elif args.command == "fetch_all":
        fetcher = MaqamFetcher()
        for record in fetcher.fetch_all():
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
