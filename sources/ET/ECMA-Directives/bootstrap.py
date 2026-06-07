#!/usr/bin/env python3
"""ET/ECMA-Directives — Ethiopian Capital Market Authority directives.

Scrapes the ECMA laws-regulation page for WPDM download links,
downloads PDFs, and extracts full text with pdfminer.
"""

import argparse
import html as htmlmod
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from pdfminer.high_level import extract_text as _pdf_extract
except ImportError:
    _pdf_extract = None

SOURCE_ID = "ET/ECMA-Directives"
PAGE_URLS = [
    "https://ecma.gov.et/laws-regulation/",
    "https://ecma.gov.et/knowledge-center/",
    "https://ecma.gov.et/",
]
SAMPLE_DIR = Path(__file__).parent / "sample"

session = requests.Session()
session.headers.update({
    "User-Agent": "LegalDataHunter/1.0 (legal-data-research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if _pdf_extract is None:
        raise ImportError("pdfminer.six required: pip install pdfminer.six")
    return _pdf_extract(io.BytesIO(pdf_bytes))


def parse_documents():
    """Parse multiple ECMA pages for WPDM download links.

    Yields (title, page_url, download_url, wpdm_id) tuples, deduped by wpdm_id.
    """
    title_pattern = re.compile(
        r'<a\s+class="package-title"\s+href=\'([^\']+)\'>([^<]+)</a>'
    )
    download_pattern = re.compile(
        r'data-downloadurl="([^"]+\?wpdmdl=(\d+)[^"]*)"'
    )

    seen_ids = set()
    for page_url_src in PAGE_URLS:
        try:
            resp = session.get(page_url_src, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [WARN] Failed to load {page_url_src}: {e}", file=sys.stderr)
            continue

        html = resp.text
        titles = title_pattern.findall(html)
        downloads = download_pattern.findall(html)

        for title_match, dl_match in zip(titles, downloads):
            page_url, raw_title = title_match
            download_url, wpdm_id = dl_match
            if wpdm_id in seen_ids:
                continue
            seen_ids.add(wpdm_id)
            title = htmlmod.unescape(raw_title).strip()
            yield title, page_url, download_url, wpdm_id
        time.sleep(1)


def classify_document(title: str) -> str:
    """Classify document type from title."""
    lower = title.lower()
    if "draft" in lower or "ረቂቅ" in title:
        return "draft_directive"
    if "proclamation" in lower:
        return "proclamation"
    if "guidance" in lower or "guideline" in lower:
        return "guideline"
    if "training" in lower or "regime" in lower:
        return "guideline"
    if "notice" in lower or "registration" in lower or "license" in lower:
        return "notice"
    if "report" in lower or "study" in lower or "assessment" in lower:
        return "report"
    if "white paper" in lower or "roadmap" in lower or "framework" in lower:
        return "policy_paper"
    if "directive" in lower:
        return "directive"
    return "other"


def normalize(title: str, page_url: str, download_url: str, wpdm_id: str, text: str) -> dict:
    doc_id = f"et-ecma-{wpdm_id}"
    return {
        "_id": doc_id,
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": None,
        "url": page_url,
        "doc_id": doc_id,
        "pdf_url": download_url,
        "document_type": classify_document(title),
    }


def fetch_all():
    """Yield all normalized documents with full text."""
    for title, page_url, download_url, wpdm_id in parse_documents():
        try:
            resp = session.get(download_url, timeout=120)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                print(f"  [SKIP] Not a PDF: {title[:60]} ({content_type})", file=sys.stderr)
                continue

            text = extract_text_from_pdf(resp.content)
            if len(text.strip()) < 50:
                print(f"  [SKIP] Insufficient text from {title[:60]}", file=sys.stderr)
                continue

            yield normalize(title, page_url, download_url, wpdm_id, text)
            time.sleep(2)
        except Exception as e:
            print(f"  [ERROR] {title[:60]}: {e}", file=sys.stderr)
            time.sleep(2)


def bootstrap_sample(limit: int = 15):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in fetch_all():
        if count >= limit:
            break
        fname = SAMPLE_DIR / f"{record['_id']}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        text_len = len(record.get("text", ""))
        print(f"  [{count+1}/{limit}] {record['title'][:60]} ({text_len} chars)")
        count += 1
    print(f"\nSaved {count} samples to {SAMPLE_DIR}")
    return count


def main():
    parser = argparse.ArgumentParser(description="ET/ECMA-Directives bootstrap")
    sub = parser.add_subparsers(dest="command")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--sample", action="store_true")
    boot.add_argument("--limit", type=int, default=15)
    boot.add_argument("--full", action="store_true")
    fast = sub.add_parser("bootstrap-fast")
    fast.add_argument("--sample", action="store_true")
    fast.add_argument("--limit", type=int, default=15)
    fast.add_argument("--full", action="store_true")
    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample or not args.full:
            count = bootstrap_sample(args.limit)
            if count < 10:
                print(f"WARNING: Only {count} samples", file=sys.stderr)
                sys.exit(1)
        else:
            for record in fetch_all():
                print(json.dumps(record, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
