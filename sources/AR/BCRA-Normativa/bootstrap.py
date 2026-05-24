#!/usr/bin/env python3
"""
AR/BCRA-Normativa -- Argentina Central Bank Communications (Comunicaciones A)

Fetches regulatory communications ("Comunicaciones A") from the BCRA
(Banco Central de la República Argentina) via the official search API.
Full text is extracted from PDFs hosted at bcra.gob.ar.

8,500+ A-type communications covering banking regulations, monetary policy,
foreign exchange rules, and financial system norms.

NO AUTH REQUIRED.

Usage:
    python bootstrap.py bootstrap --sample   # Fetch 15 sample records
    python bootstrap.py bootstrap --full     # Full incremental fetch
    python bootstrap.py updates --since YYYY-MM-DD
"""

import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import requests
from pdfminer.high_level import extract_text as pdfminer_extract

SCRIPT_DIR = Path(__file__).parent
SAMPLE_DIR = SCRIPT_DIR / "sample"
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

SOURCE_ID = "AR/BCRA-Normativa"
BASE_URL = "https://www.bcra.gob.ar"
API_URL = f"{BASE_URL}/api/endpoints/buscador-comunicaciones.php"
PDF_BASE = f"{BASE_URL}/archivos"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_DELAY = 1.5
PAGE_SIZE = 100


class BCRAClient:
    """Client for BCRA communications search API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def search(
        self,
        tipo: str = "A",
        fecha_desde: str = "1935-01-01",
        fecha_hasta: str = "2099-12-31",
        page: int = 1,
        page_size: int = PAGE_SIZE,
        retries: int = 3,
    ) -> Optional[Dict]:
        """Search communications by type and date range."""
        data = {
            "mode": "tipo-fecha",
            "tipo": tipo,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "paginaabsoluta": page,
            "tamanopagina": page_size,
            "lang": "es",
        }
        for attempt in range(retries):
            try:
                resp = self.session.post(API_URL, data=data, timeout=30)
                if resp.status_code == 429:
                    time.sleep(2 ** (attempt + 2))
                    continue
                resp.raise_for_status()
                result = resp.json()
                if result.get("success"):
                    return result["data"]
                print(f"  API error: {result.get('error', 'unknown')}")
                return None
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
                print(f"  Search failed: {exc}")
                return None
        return None

    def download_pdf(self, pdf_path: str, retries: int = 3) -> Optional[bytes]:
        """Download a PDF from BCRA servers."""
        url = f"{BASE_URL}{pdf_path}" if pdf_path.startswith("/") else pdf_path
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 429:
                    time.sleep(2 ** (attempt + 2))
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                if b"%PDF" in resp.content[:20]:
                    return resp.content
                return None
            except requests.RequestException:
                if attempt < retries - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
                return None
        return None


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer."""
    try:
        text = pdfminer_extract(io.BytesIO(pdf_bytes))
        # Clean up whitespace
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            line = line.rstrip()
            cleaned.append(line)
        return "\n".join(cleaned).strip()
    except Exception as exc:
        print(f"  PDF extraction error: {exc}")
        return ""


def normalize(record: Dict, text: str) -> Dict:
    """Normalize a BCRA communication into the standard schema."""
    tipo = record.get("tipo", "A")
    numero = record.get("numero_formateado", "")
    doc_id = f"{tipo}{numero}"

    return {
        "_id": f"AR/BCRA-Normativa/{doc_id}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": record.get("titulo", "").strip(),
        "text": text,
        "date": record.get("fecha_emision", None),
        "url": f"{BASE_URL}{record.get('pdf_path', '')}",
        "communication_type": tipo,
        "communication_number": numero,
        "boletín_number": record.get("nro_boletin"),
        "boletín_date": record.get("fecha_boletin", "").strip() or None,
    }


def fetch_sample(count: int = 15) -> List[Dict]:
    """Fetch sample communications (most recent A-type)."""
    client = BCRAClient()
    records: List[Dict] = []

    print("Searching for recent A-type communications...")
    data = client.search(tipo="A", page=1, page_size=count + 5)
    time.sleep(REQUEST_DELAY)

    if not data:
        print("  No results from API")
        return records

    items = data.get("registros", [])
    total = data.get("pagination", {}).get("totalRecords", 0)
    print(f"  Total A-type communications: {total:,}")
    print(f"  Fetching {len(items)} items from first page...")

    for item in items:
        if len(records) >= count:
            break

        pdf_path = item.get("pdf_path", "")
        if not pdf_path:
            print(f"  Skipping {item.get('tipo','')}{item.get('numero_formateado','')}: no PDF path")
            continue

        doc_id = f"{item.get('tipo','A')}{item.get('numero_formateado','')}"
        print(f"  [{len(records)+1}] {doc_id} - {item.get('titulo', '')[:60]}...")
        print(f"       Downloading PDF...")

        pdf_bytes = client.download_pdf(pdf_path)
        time.sleep(REQUEST_DELAY)

        if not pdf_bytes:
            print(f"       Skipping: PDF download failed")
            continue

        text = extract_text(pdf_bytes)
        if len(text) < 100:
            print(f"       Skipping: text too short ({len(text)} chars)")
            continue

        record = normalize(item, text)
        records.append(record)
        print(f"       OK: {len(text):,} chars")

    return records


def fetch_all(sample: bool = False, since: Optional[str] = None) -> Generator[Dict, None, None]:
    """Fetch all A-type communications."""
    if sample:
        yield from fetch_sample()
        return

    client = BCRAClient()
    total_yielded = 0
    page = 1

    fecha_desde = since if since else "1935-01-01"
    fecha_hasta = datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching A-type communications from {fecha_desde} to {fecha_hasta}...")

    while True:
        data = client.search(tipo="A", fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, page=page)
        time.sleep(REQUEST_DELAY)

        if not data:
            break

        items = data.get("registros", [])
        pagination = data.get("pagination", {})
        total_pages = pagination.get("totalPages", 0)
        total_records = pagination.get("totalRecords", 0)

        if not items:
            break

        if page == 1:
            print(f"  Total records: {total_records:,}, pages: {total_pages}")

        for item in items:
            pdf_path = item.get("pdf_path", "")
            if not pdf_path:
                continue

            pdf_bytes = client.download_pdf(pdf_path)
            time.sleep(REQUEST_DELAY)
            if not pdf_bytes:
                continue

            text = extract_text(pdf_bytes)
            if len(text) < 100:
                continue

            record = normalize(item, text)
            total_yielded += 1
            if total_yielded % 50 == 0:
                print(f"  Fetched {total_yielded} records (page {page}/{total_pages})...")
            yield record

        if page >= total_pages:
            break
        page += 1

    print(f"  Total fetched: {total_yielded}")


def save_samples(records: List[Dict]) -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(records):
        with open(SAMPLE_DIR / f"record_{i:04d}.json", "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
    with open(SAMPLE_DIR / "all_samples.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(records)} samples to {SAMPLE_DIR}")


def validate_samples() -> bool:
    samples = sorted(SAMPLE_DIR.glob("record_*.json"))
    if len(samples) < 10:
        print(f"FAIL: Only {len(samples)} samples, need >= 10")
        return False

    ok = True
    text_lengths = []
    for p in samples:
        with open(p, "r", encoding="utf-8") as f:
            rec = json.load(f)
        text = rec.get("text", "")
        text_lengths.append(len(text))
        if not text:
            print(f"FAIL: {p.name} missing text")
            ok = False
        for field in ("_id", "_source", "_type", "title", "date"):
            if not rec.get(field):
                print(f"WARN: {p.name} missing {field}")

    avg = sum(text_lengths) / len(text_lengths) if text_lengths else 0
    print(f"\nValidation:")
    print(f"  Samples: {len(samples)}")
    print(f"  Avg text: {avg:,.0f} chars")
    print(f"  Min text: {min(text_lengths):,} chars")
    print(f"  Max text: {max(text_lengths):,} chars")
    print(f"  Valid: {ok}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="AR/BCRA-Normativa fetcher")
    sub = parser.add_subparsers(dest="command")
    bp = sub.add_parser("bootstrap")
    bp.add_argument("--sample", action="store_true")
    bp.add_argument("--full", action="store_true")
    up = sub.add_parser("updates")
    up.add_argument("--since", required=True)
    sub.add_parser("validate")
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        sys.exit(0 if validate_samples() else 1)

    if args.command == "bootstrap":
        if args.sample:
            print("Fetching sample BCRA A-type communications...")
            records = fetch_sample()
            if records:
                save_samples(records)
                validate_samples()
                sys.exit(0 if len(records) >= 10 else 1)
            else:
                print("No records fetched!", file=sys.stderr)
                sys.exit(1)
        elif args.full:
            count = 0
            for _ in fetch_all():
                count += 1
            print(f"Fetched {count} A-type communications")
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "updates":
        count = 0
        for _ in fetch_all(since=args.since):
            count += 1
        print(f"Fetched {count} updates since {args.since}")


if __name__ == "__main__":
    main()
