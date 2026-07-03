#!/usr/bin/env python3
"""
EC/CNJ-Precedentes -- Ecuador Corte Nacional de Justicia Binding Precedents

Fetches mandatory jurisprudential precedents (triple-reiteration rule) from the
Corte Nacional de Justicia. These are the highest-value binding case law decisions
in Ecuador's judicial system.

The listing page at /resoluciones-a/precedentes-jurisprudenciales contains ~60+
direct PDF links organized by year (2009-2026). Each PDF is a full resolution
with the court's binding legal reasoning.

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # Sample (15 docs)
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Connectivity test
"""

import io
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import urljoin

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.EC.CNJ-Precedentes")

BASE_URL = "https://www.cortenacional.gob.ec"
LISTING_URL = f"{BASE_URL}/cnj/index.php/resoluciones-a/precedentes-jurisprudenciales"


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


class CNJPrecedentesScraper(BaseScraper):
    """
    Scraper for EC/CNJ-Precedentes.
    Country: EC
    URL: https://www.cortenacional.gob.ec/cnj/index.php/resoluciones-a/precedentes-jurisprudenciales

    Data types: case_law
    Auth: none
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LegalDataHunter/1.0 (open-data research project)",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })

    def _parse_listing(self) -> list[dict]:
        """Parse the listing page and extract PDF links with metadata."""
        resp = self.session.get(LISTING_URL, timeout=60)
        resp.raise_for_status()
        html = resp.text

        documents = []
        for match in re.finditer(r'href="([^"]*\.pdf)"', html):
            pdf_path = match.group(1)
            pdf_url = urljoin(BASE_URL, pdf_path)

            # Extract resolution number and year from filename
            filename = pdf_path.split("/")[-1]
            # e.g., "02-2026_Jurisprudencia_obligatoria_-_Obligacion_..."
            # or "2024-21-Jurisprudencia-obligatoria---pago-indebido..."
            num_match = re.search(r"(\d{1,2})-(\d{4})", filename)
            if not num_match:
                num_match = re.search(r"(\d{4})-(\d{1,2})", filename)

            if num_match:
                groups = num_match.groups()
                if len(groups[0]) == 4:
                    year, num = groups[0], groups[1]
                else:
                    num, year = groups[0], groups[1]
                res_id = f"{num.zfill(2)}-{year}"
            else:
                res_id = filename.replace(".pdf", "")[:20]
                year = re.search(r"/(\d{4})/", pdf_path)
                year = year.group(1) if year else ""

            # Extract topic from filename
            topic = filename.replace(".pdf", "")
            topic = re.sub(r"^\d+-\d+[-_]", "", topic)
            topic = re.sub(r"^\d{4}-\d+[-_]", "", topic)
            topic = topic.replace("_", " ").replace("-", " ").replace("---", " — ")
            topic = re.sub(r"\s+", " ", topic).strip()

            # Get context around the link for title
            start = max(0, match.start() - 500)
            context = html[start:match.start()]
            # Look for "Resolución No. XX-YYYY:" pattern
            title_match = re.search(
                r"Resolución\s+No\.\s*(\d+[-/]\d+)[:\s]*(.{0,200}?)(?:<|$)",
                context, re.DOTALL
            )
            if title_match:
                title = f"Resolución No. {title_match.group(1)}"
                desc = re.sub(r"<[^>]+>", "", title_match.group(2)).strip()
                desc = re.sub(r"&nbsp;", " ", desc)
                if desc:
                    title = f"{title}: {desc[:150]}"
            else:
                title = f"Resolución No. {res_id}: {topic[:100]}"

            documents.append({
                "res_id": res_id,
                "year": year,
                "title": title,
                "topic": topic,
                "pdf_url": pdf_url,
                "filename": filename,
            })

        # Deduplicate by PDF URL
        seen = set()
        unique = []
        for doc in documents:
            if doc["pdf_url"] not in seen:
                seen.add(doc["pdf_url"])
                unique.append(doc)

        logger.info(f"Parsed {len(unique)} precedent resolutions from listing page")
        return unique

    def normalize(self, raw: dict) -> dict:
        """Transform raw data into standard schema."""
        return {
            "_id": f"EC/CNJ-Precedentes/{raw['res_id']}",
            "_source": "EC/CNJ-Precedentes",
            "_type": "case_law",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw.get("text", ""),
            "date": f"{raw['year']}-01-01" if raw.get("year") else None,
            "url": raw["pdf_url"],
            "resolution_number": raw["res_id"],
            "topic": raw.get("topic", ""),
        }

    def fetch_all(self, sample: bool = False) -> Generator[dict, None, None]:
        """Yield all binding precedent resolutions with full text."""
        documents = self._parse_listing()

        if sample:
            # Pick diverse sample: first 5, middle 5, last 5
            n = len(documents)
            indices = list(range(min(5, n)))
            indices += list(range(n // 2 - 2, min(n // 2 + 3, n)))
            indices += list(range(max(0, n - 5), n))
            indices = sorted(set(i for i in indices if 0 <= i < n))
            documents = [documents[i] for i in indices]
            logger.info(f"Sample mode: selected {len(documents)} documents")

        for i, doc in enumerate(documents):
            logger.info(f"[{i+1}/{len(documents)}] Fetching: {doc['title'][:80]}...")

            try:
                resp = self.session.get(doc["pdf_url"], timeout=60)
                resp.raise_for_status()
                text = extract_pdf_text(resp.content)
            except Exception as e:
                logger.warning(f"  Failed to download PDF: {e}")
                continue

            if not text or len(text) < 200:
                logger.warning(f"  Insufficient text ({len(text)} chars) for {doc['res_id']}")
                continue

            doc["text"] = text
            record = self.normalize(doc)
            yield record

            time.sleep(1.5)

    def fetch_updates(self, since: str) -> Generator[dict, None, None]:
        """Re-fetch all (small corpus, no incremental API)."""
        yield from self.fetch_all()

    def test_connection(self) -> bool:
        """Test connectivity to the CNJ website."""
        try:
            resp = self.session.get(LISTING_URL, timeout=15)
            resp.raise_for_status()
            pdfs = re.findall(r'href="[^"]*\.pdf"', resp.text)
            if pdfs:
                logger.info(f"Connection OK: {len(pdfs)} PDF links found")
                return True
            else:
                logger.error("Page loaded but no PDF links found")
                return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False


def main():
    scraper = CNJPrecedentesScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|update|test] [--sample]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv

    if command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        total_text = 0
        for record in scraper.fetch_all(sample=sample):
            text_len = len(record.get("text", ""))
            total_text += text_len
            count += 1

            fname = re.sub(r"[^\w\-.]", "_", record["_id"]) + ".json"
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            logger.info(f"  Saved: {fname} ({text_len:,} chars)")

        avg = total_text // count if count else 0
        logger.info(f"Done: {count} records, avg text {avg:,} chars")

    elif command == "update":
        for record in scraper.fetch_updates(""):
            pass

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
