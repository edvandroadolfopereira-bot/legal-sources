#!/usr/bin/env python3
"""
PA/CENDOJ -- Panama CENDOJ "Fallos de Interés" (significant Supreme Court rulings)

Fetches the curated collection of significant rulings ("fallos de interés")
published by the Centro de Documentación Judicial (CENDOJ) of Panama's Órgano
Judicial at:

    https://www.organojudicial.gob.pa/cendoj/files/fallos-de-interes

The listing is a paginated server-rendered page (?page=N). Each entry links to a
ruling PDF hosted under /uploads/blogs.dir/. Most of the legally interesting
documents — Supreme Court (Corte Suprema de Justicia) unconstitutionality
rulings, contentious-administrative decisions, habeas corpus/data decisions, and
jurisprudential digests ("extractos"/"recopilaciones") — are born-digital PDFs
with a real text layer. A minority are signed scans with no text layer; those
are detected (low chars-per-page) and skipped so only real full text is emitted.

The full text lives in the PDF, extracted here with PyMuPDF (fitz).

Usage:
  python bootstrap.py test-api
  python bootstrap.py bootstrap --sample
  python bootstrap.py bootstrap
  python bootstrap.py bootstrap-fast
"""

import argparse
import html as htmllib
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip3 install pymupdf")
    sys.exit(1)

SOURCE_ID = "PA/CENDOJ"
SOURCE_DIR = Path(__file__).parent
SAMPLE_DIR = SOURCE_DIR / "sample"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.PA.CENDOJ")

LISTING_URL = "https://www.organojudicial.gob.pa/cendoj/files/fallos-de-interes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    # The site returns a stub page unless an HTML Accept header is sent.
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 1.5       # seconds between requests (robots.txt allows all)
MAX_PAGES = 30            # safety cap on listing pagination
LISTING_RETRIES = 4       # retries when the listing page hits the Radware bot wall
HOME_URL = "https://www.organojudicial.gob.pa/"
MIN_TEXT_CHARS = 2000     # below this we treat the PDF as having no usable text
MIN_CHARS_PER_PAGE = 150  # filters scanned PDFs that yield only a thin OCR cover

# Each listing card: <a href="...pdf" id="estilo_titulo"> ... <h5>TITLE</h5> </a>
ENTRY_RE = re.compile(
    r'<a href="([^"]+\.pdf)"[^>]*id="estilo_titulo"[^>]*>(.*?)</a>', re.S
)
H5_RE = re.compile(r"<h5[^>]*>(.*?)</h5>", re.S)
DATE_RE = re.compile(r"Fecha de publicaci[^:]*:</b>\s*([^<|]+)")
TAG_RE = re.compile(r"<[^>]+>")

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Titles starting with these markers are jurisprudential digests / compilations
# (doctrine) rather than a single judicial decision (case_law).
DOCTRINE_MARKERS = ("extracto", "recopilaci", "resena", "reseña")


def clean_text(raw: str) -> str:
    """Collapse whitespace and decode entities into clean plain text."""
    if not raw:
        return ""
    text = htmllib.unescape(raw)
    text = text.replace("\xa0", " ")
    # Normalise newlines: keep paragraph breaks, collapse runs of spaces.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_tags(raw: str) -> str:
    return clean_text(TAG_RE.sub(" ", raw))


def parse_spanish_date(raw: str) -> Optional[str]:
    """'Viernes, 27 Dic 2024' -> '2024-12-27' (ISO). Returns None if unparseable."""
    if not raw:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+(\d{4})", raw)
    if not m:
        return None
    day = int(m.group(1))
    mon = SPANISH_MONTHS.get(m.group(2)[:3].lower())
    year = int(m.group(3))
    if not mon:
        return None
    try:
        return datetime(year, mon, day).date().isoformat()
    except ValueError:
        return None


def slug_id(pdf_url: str) -> str:
    """Derive a stable id from the PDF filename."""
    name = pdf_url.rstrip("/").split("/")[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return f"PA-CENDOJ-{name[:120]}"


def classify(title: str) -> str:
    low = title.lower()
    return "doctrine" if any(m in low for m in DOCTRINE_MARKERS) else "case_law"


def parse_listing(html: str) -> list:
    """Parse one listing page into a list of entry dicts."""
    entries = []
    for m in ENTRY_RE.finditer(html):
        pdf = htmllib.unescape(m.group(1))
        inner = m.group(2)
        h5 = H5_RE.search(inner)
        title = strip_tags(h5.group(1)) if h5 else ""
        tail = html[m.end():m.end() + 600]
        dm = DATE_RE.search(tail)
        date_raw = strip_tags(dm.group(1)) if dm else ""
        entries.append({"pdf": pdf, "title": title, "date_raw": date_raw})
    return entries


def _is_captcha(text: str) -> bool:
    return "Radware Captcha" in text or "perfdrive.com" in text


def warm_session(session: requests.Session) -> None:
    """Hit the homepage once so the WAF issues session cookies before scraping."""
    try:
        session.get(HOME_URL, timeout=40)
        time.sleep(REQUEST_DELAY)
    except requests.exceptions.RequestException:
        pass


def fetch_listing_page(session: requests.Session, url: str) -> Optional[str]:
    """Fetch one listing page, retrying with backoff through the Radware bot wall."""
    backoff = 5
    for attempt in range(1, LISTING_RETRIES + 1):
        try:
            resp = session.get(url, timeout=60)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Listing request error ({url}) attempt {attempt}: {e}")
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code == 200 and "estilo_titulo" in resp.text:
            return resp.text
        if _is_captcha(resp.text) or resp.status_code in (302, 403, 503):
            logger.warning(
                f"Bot wall on {url} (status {resp.status_code}); "
                f"retry {attempt}/{LISTING_RETRIES} after {backoff}s"
            )
            time.sleep(backoff)
            backoff *= 2
            warm_session(session)
            continue
        # 200 but no entries (past last page) — return as-is.
        return resp.text
    return None


def iter_listing(session: requests.Session) -> Generator[dict, None, None]:
    """Yield every entry across all listing pages (dedup by PDF URL)."""
    warm_session(session)
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        html = fetch_listing_page(session, url)
        if html is None:
            logger.error(f"Listing page {page} unreachable (bot wall); stopping pagination")
            break
        entries = parse_listing(html)
        new = 0
        for e in entries:
            if e["pdf"] in seen:
                continue
            seen.add(e["pdf"])
            new += 1
            yield e
        logger.info(f"Listing page {page}: {new} new entries (total {len(seen)})")
        if new == 0:
            break
        time.sleep(REQUEST_DELAY)


def extract_pdf_text(pdf_bytes: bytes) -> tuple:
    """Return (clean_text, page_count) from a PDF's text layer."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"PDF open failed: {e}")
        return "", 0
    parts = []
    for page in doc:
        t = page.get_text("text") or ""
        if t.strip():
            parts.append(t)
    pages = doc.page_count
    doc.close()
    return clean_text("\n".join(parts)), pages


def normalize(entry: dict, text: str, pages: int) -> dict:
    title = entry["title"] or entry["pdf"].split("/")[-1]
    return {
        "_id": slug_id(entry["pdf"]),
        "_source": SOURCE_ID,
        "_type": classify(title),
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "text": text,
        "date": parse_spanish_date(entry["date_raw"]),
        "url": LISTING_URL,
        "pdf_url": entry["pdf"],
        "pages": pages,
        "court": "Corte Suprema de Justicia de Panamá",
        "publisher": "Centro de Documentación Judicial (CENDOJ), Órgano Judicial de Panamá",
        "language": "spa",
        "country": "PA",
    }


def _is_full_text(text: str, pages: int) -> bool:
    if len(text) < MIN_TEXT_CHARS:
        return False
    if pages and (len(text) / pages) < MIN_CHARS_PER_PAGE:
        return False
    return True


def fetch_all(limit: Optional[int] = None) -> Generator[dict, None, None]:
    """Yield normalized full-text records for every born-digital ruling PDF."""
    session = requests.Session()
    session.headers.update(HEADERS)
    total = 0
    skipped = 0
    for entry in iter_listing(session):
        try:
            r = session.get(entry["pdf"], timeout=90)
            r.raise_for_status()
            data = r.content
        except requests.exceptions.RequestException as e:
            logger.warning(f"PDF download failed {entry['pdf']}: {e}")
            time.sleep(REQUEST_DELAY)
            continue
        if not data[:5].startswith(b"%PDF"):
            logger.warning(f"Not a PDF (bot wall?) {entry['pdf']}")
            time.sleep(REQUEST_DELAY)
            continue
        text, pages = extract_pdf_text(data)
        time.sleep(REQUEST_DELAY)
        if not _is_full_text(text, pages):
            skipped += 1
            logger.debug(f"Skip (no usable text, {len(text)}c/{pages}p): {entry['pdf']}")
            continue
        yield normalize(entry, text, pages)
        total += 1
        if limit and total >= limit:
            logger.info(f"Reached limit of {limit} records")
            return
    logger.info(f"Emitted {total} full-text records; skipped {skipped} scanned/empty PDFs")


def fetch_updates(since: str, limit: Optional[int] = None) -> Generator[dict, None, None]:
    """Yield records whose listing publication date is on/after `since` (ISO date)."""
    count = 0
    for rec in fetch_all():
        if rec["date"] and rec["date"] >= since:
            yield rec
            count += 1
            if limit and count >= limit:
                return


def test_api():
    """Probe the listing and extract one sample full-text ruling."""
    logger.info("Testing CENDOJ listing access...")
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        resp = session.get(LISTING_URL, timeout=60)
        resp.raise_for_status()
        entries = parse_listing(resp.text)
        logger.info(f"Listing page 1 parsed: {len(entries)} entries")
        for e in entries[:3]:
            logger.info(f"  - [{e['date_raw']}] {e['title'][:60]}")
        logger.info("\nFetching one sample full-text ruling...")
        for rec in fetch_all(limit=1):
            logger.info(f"  {rec['title']}  ({len(rec['text']):,} chars, {rec['pages']}p)")
            logger.info(f"  PDF: {rec['pdf_url']}")
            logger.info(f"  Preview: {rec['text'][:200]}...")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Test failed: {e}")
        sys.exit(1)


def bootstrap(sample: bool = False, full: bool = False, sample_size: int = 15):
    limit = sample_size if sample else None
    out_dir = SAMPLE_DIR if sample else SOURCE_DIR / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    text_lengths = []
    for record in fetch_all(limit=limit):
        records.append(record)
        text_lengths.append(len(record.get("text", "")))
        safe_id = record["_id"].replace("/", "_").replace(" ", "_")
        with open(out_dir / f"{safe_id}.json", "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {record['_id']} ({len(record.get('text', '')):,} chars)")

    if records:
        avg_text = sum(text_lengths) / len(text_lengths)
        logger.info(f"\n{'='*60}")
        logger.info(f"Total records: {len(records)}")
        logger.info(f"Avg text length: {avg_text:,.0f} chars")
        logger.info(f"Min text length: {min(text_lengths):,} chars")
        logger.info(f"Max text length: {max(text_lengths):,} chars")
        logger.info(f"Records with text: {sum(1 for t in text_lengths if t > 0)}/{len(records)}")
        logger.info(f"Output directory: {out_dir}")
    else:
        logger.warning("No records fetched!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PA/CENDOJ data fetcher")
    parser.add_argument("command", choices=["test-api", "bootstrap", "bootstrap-fast"])
    parser.add_argument("--sample", action="store_true", help="Fetch sample only")
    parser.add_argument("--sample-size", type=int, default=15, help="Sample size")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    parser.add_argument("--since", help="For updates: ISO date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.command == "test-api":
        test_api()
    else:  # bootstrap / bootstrap-fast
        bootstrap(sample=args.sample, full=args.full, sample_size=args.sample_size)
