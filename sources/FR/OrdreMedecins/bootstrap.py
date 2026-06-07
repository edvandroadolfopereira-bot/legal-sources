#!/usr/bin/env python3
"""
FR/OrdreMedecins - Ordre des Médecins Disciplinary Decisions Fetcher

Fetches disciplinary decisions from the French Medical Order's jurisprudence
database (Chambre disciplinaire nationale and regional chambers).

Data source: https://www.jurisprudence.ordre.medecin.fr/
License: Licence Ouverte 2.0

The site uses Struts 2 with server-side conversation state. Each detail page
contains metadata + abstract. Full decision text is obtained via PDF export
(requires posting CTX token back to the form).

Usage:
  python bootstrap.py bootstrap --sample  # Fetch 15 sample records
  python bootstrap.py bootstrap            # Full bootstrap (all ~20K+ decisions)
  python bootstrap.py updates --since YYYY-MM-DD  # Not supported (no date filter API)
"""

import argparse
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Generator, Optional

import pdfplumber
import requests

SOURCE_ID = "FR/OrdreMedecins"
BASE_URL = "https://www.jurisprudence.ordre.medecin.fr"
DETAIL_URL = BASE_URL + "/FicheDetailConsultation.do?ficId={fic_id}&isFromRecherche=listeResultats"

HEADERS = {
    "User-Agent": "Legal Data Hunter/1.0 (EU Legal Research; Open Data Collection)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

SAMPLE_DIR = Path(__file__).parent / "sample"

# Known valid ficId range (non-sequential, with gaps)
MIN_FIC_ID = 1
MAX_FIC_ID = 23000


def clean_html(html_text: str) -> str:
    """Remove HTML tags and clean text."""
    if not html_text:
        return ""
    text = unescape(html_text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_detail_page(html: str, fic_id: int) -> Optional[dict]:
    """Parse the detail page HTML to extract metadata."""
    if 'ABSTRACT' not in html:
        return None

    result = {"fic_id": fic_id}

    # Extract instance/jurisdiction
    m = re.search(
        r'fiche_juridictionLibelleHighlight.*?<td[^>]*>\s*<div>\s*(.*?)\s*</div>',
        html, re.DOTALL
    )
    if m:
        result["instance"] = clean_html(m.group(1)).strip()

    # Extract date
    m = re.search(r'datepicker_\d+["\'][^>]*>(\d{2}/\d{2}/\d{4})', html)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d/%m/%Y")
            result["date"] = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Extract document type
    m = re.search(
        r'typeDocumentHighlight.*?<td[^>]*>\s*<div>\s*(.*?)\s*</div>',
        html, re.DOTALL
    )
    if m:
        result["doc_type"] = clean_html(m.group(1)).strip()

    # Extract dossier number
    m = re.search(
        r'numeroDossierHighlight.*?<td[^>]*>\s*<div>\s*(.*?)\s*</div>',
        html, re.DOTALL
    )
    if m:
        result["dossier_number"] = clean_html(m.group(1)).strip()

    # Extract keywords
    keywords = re.findall(r'<hlfrag>(.*?)</hlfrag>', html)
    if keywords:
        result["keywords"] = [clean_html(k) for k in keywords
                              if k not in ("Plaignant", "Requérant", "Poursuivi",
                                           "Partie dans l'affaire")]

    # Extract abstract
    m = re.search(
        r'<h2[^>]*>ABSTRACT</h2>\s*<div[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    if m:
        result["abstract"] = clean_html(m.group(1)).strip()

    # Extract articles referenced
    m = re.search(
        r'code sant.*?publique.*?<td[^>]*>\s*<div>\s*(.*?)\s*</div>',
        html, re.DOTALL | re.IGNORECASE
    )
    if m:
        result["articles_csp"] = clean_html(m.group(1)).strip()

    # Extract CTX token for PDF export
    m = re.search(r'name="CTX"\s+value="([^"]+)"', html)
    if m:
        result["ctx"] = m.group(1)

    # Extract jsessionid
    m = re.search(r'jsessionid=([A-Z0-9.]+)', html)
    if m:
        result["jsessionid"] = m.group(1)

    return result


def export_decision_pdf(session: requests.Session, metadata: dict) -> Optional[bytes]:
    """Export the full decision PDF using the Struts 2 conversation context."""
    ctx = metadata.get("ctx")
    jsessionid = metadata.get("jsessionid")
    if not ctx or not jsessionid:
        return None

    export_url = f"{BASE_URL}/FicheDetailConsultation.do;jsessionid={jsessionid}"
    data = {
        "CTX": ctx,
        "action:FicheDetailConsultationExportDecision": "",
    }
    headers = {
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": DETAIL_URL.format(fic_id=metadata["fic_id"]),
    }

    try:
        resp = session.post(export_url, data=data, headers=headers, timeout=30)
        if resp.status_code == 200 and resp.headers.get("Content-Disposition"):
            return resp.content
    except requests.RequestException:
        pass
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except Exception:
        return ""


def normalize(metadata: dict, full_text: str) -> dict:
    """Normalize a decision into the standard schema."""
    fic_id = metadata["fic_id"]
    dossier = metadata.get("dossier_number", str(fic_id))
    instance = metadata.get("instance", "Chambre disciplinaire")
    date = metadata.get("date", "")

    title = f"{instance} — Dossier n° {dossier}"
    if date:
        title += f" — {date}"

    return {
        "_id": f"ordre-medecins-{fic_id}",
        "_source": SOURCE_ID,
        "_type": "case_law",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": full_text,
        "date": date or None,
        "url": DETAIL_URL.format(fic_id=fic_id),
        "dossier_number": dossier,
        "instance": instance,
        "doc_type": metadata.get("doc_type", ""),
        "keywords": metadata.get("keywords", []),
        "abstract": metadata.get("abstract", ""),
        "articles_csp": metadata.get("articles_csp", ""),
    }


def fetch_decision(session: requests.Session, fic_id: int) -> Optional[dict]:
    """Fetch a single decision by ficId: metadata + full text PDF.

    Uses a fresh session per request because Struts 2 conversation state
    conflicts when the same session visits multiple ficId pages.
    """
    # Fresh session to avoid Struts 2 CTX token conflicts
    sess = requests.Session()
    url = DETAIL_URL.format(fic_id=fic_id)
    try:
        resp = sess.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    metadata = parse_detail_page(resp.text, fic_id)
    if not metadata:
        return None

    # Export and extract PDF using same session (preserves CTX state)
    pdf_bytes = export_decision_pdf(sess, metadata)
    if not pdf_bytes:
        # Fall back to abstract only if PDF export fails
        full_text = metadata.get("abstract", "")
        if not full_text:
            return None
    else:
        full_text = extract_pdf_text(pdf_bytes)
        if not full_text:
            full_text = metadata.get("abstract", "")

    return normalize(metadata, full_text)


def fetch_all(sample: bool = False) -> Generator[dict, None, None]:
    """Yield all decisions, iterating through ficId values."""
    session = requests.Session()
    count = 0
    target = 15 if sample else 999999
    errors_in_row = 0

    # For sample mode, use known-good recent ficIds to save time
    if sample:
        # Scan from recent IDs backward to find valid ones quickly
        fic_ids = range(22500, 19000, -1)
    else:
        fic_ids = range(MAX_FIC_ID, MIN_FIC_ID - 1, -1)

    for fic_id in fic_ids:
        if count >= target:
            break

        record = fetch_decision(session, fic_id)
        if record is None:
            errors_in_row += 1
            if errors_in_row > 50 and sample:
                # Too many misses, skip ahead
                break
            continue

        errors_in_row = 0

        if len(record.get("text", "")) < 100:
            print(f"  [SKIP] ficId={fic_id}: text too short ({len(record.get('text', ''))} chars)")
            continue

        count += 1
        print(f"  [{count}/{target}] ficId={fic_id}: {record['title'][:60]}... ({len(record['text'])} chars)")
        yield record

        # Rate limiting
        time.sleep(2.0)

    print(f"\nTotal records fetched: {count}")


def save_samples(records: list):
    """Save sample records to the sample/ directory."""
    SAMPLE_DIR.mkdir(exist_ok=True)
    for i, record in enumerate(records, 1):
        path = SAMPLE_DIR / f"record_{i:03d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"  Saved: {path.name}")


def main():
    parser = argparse.ArgumentParser(description="FR/OrdreMedecins bootstrap")
    subparsers = parser.add_subparsers(dest="command")

    boot_parser = subparsers.add_parser("bootstrap", help="Fetch records")
    boot_parser.add_argument("--sample", action="store_true", help="Fetch 15 sample records only")

    updates_parser = subparsers.add_parser("updates", help="Fetch updates (not supported)")
    updates_parser.add_argument("--since", required=True, help="Date (not used)")

    args = parser.parse_args()

    if args.command == "bootstrap":
        print(f"FR/OrdreMedecins bootstrap ({'sample' if args.sample else 'full'} mode)")
        print(f"Source: {BASE_URL}")
        print()

        records = list(fetch_all(sample=args.sample))

        if args.sample and records:
            save_samples(records)
            print(f"\n{len(records)} sample records saved to {SAMPLE_DIR}/")
        elif records:
            # In full mode, write JSONL to stdout
            for r in records:
                print(json.dumps(r, ensure_ascii=False))

    elif args.command == "updates":
        print("Updates not supported for this source (no date-filtered API).")
        sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
