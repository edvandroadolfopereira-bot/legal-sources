#!/usr/bin/env python3
"""
KM/MinistryOfJustice -- Comoros Ministry of Justice legislation

Fetches the consolidated body of Comorian law (lois, décrets, ordonnances,
codes, arrêtés) from the official Ministère de la Justice portal
(justice.gouv.km). Documents are enumerated via the Yoast text sitemap
(texte-sitemap1.xml). Each /texte/{slug}/ page carries the full text either
inline in <div class="the-content"> or as a linked PDF under
/wp-content/uploads/. Full text is taken from whichever is longer.

Scanned-image PDFs with no text layer are skipped (no OCR available).

Usage:
  python bootstrap.py bootstrap                       # Full pull
  python bootstrap.py bootstrap --sample              # 12 sample records
  python bootstrap.py bootstrap --sample --sample-size 10
  python bootstrap.py bootstrap-fast                  # Concurrent full pull
  python bootstrap.py test                            # Connectivity test
"""

import sys
import io
import re
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, Optional, List, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.KM.MinistryOfJustice")

BASE_URL = "https://justice.gouv.km"
SITEMAP_URL = BASE_URL + "/texte-sitemap1.xml"

MIN_TEXT_CHARS = 400  # below this we treat the page as "no full text" (intro only)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LegalDataHunter/1.0; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
    "Accept-Language": "fr,en;q=0.8",
}

_PDF_RE = re.compile(
    r"https://justice\.gouv\.km/wp-content/uploads/[^\"'<>\s]+\.pdf", re.I
)

_FR_MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
    r"septembre|octobre|novembre|d[eé]cembre)\s+(\d{4})",
    re.I,
)


def _encode_url(u: str) -> str:
    """Percent-encode the path of a URL (handles °, accents, spaces)."""
    p = urlsplit(u)
    return urlunsplit((p.scheme, p.netloc, quote(p.path), p.query, p.fragment))


class KMMinistryOfJusticeScraper(BaseScraper):
    """Scraper for KM/MinistryOfJustice — Comoros legislation."""

    def __init__(self):
        super().__init__(Path(__file__).parent)
        self.session = None

    # ── HTTP ──────────────────────────────────────────────────────────
    def _get_session(self):
        if self.session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            self.session = requests.Session()
            self.session.headers.update(_HEADERS)
            retry = Retry(
                total=3, backoff_factor=2,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        return self.session

    def _get_html(self, url: str) -> Optional[str]:
        """GET a page, retrying until a substantive response comes back."""
        sess = self._get_session()
        last = None
        for attempt in range(3):
            try:
                resp = sess.get(url, timeout=40)
                last = resp.text
                if resp.status_code == 200 and len(resp.text) > 3000:
                    return resp.text
            except Exception as e:
                logger.debug(f"GET failed ({attempt}) {url}: {e}")
            time.sleep(1.5)
        return last

    def _get_pdf(self, url: str) -> Optional[bytes]:
        sess = self._get_session()
        try:
            resp = sess.get(_encode_url(url), timeout=90)
            resp.raise_for_status()
            if len(resp.content) < 200:
                return None
            return resp.content
        except Exception as e:
            logger.debug(f"PDF download failed {url}: {e}")
            return None

    # ── Extraction helpers ────────────────────────────────────────────
    @staticmethod
    def _pdf_text(pdf_bytes: bytes) -> str:
        """Extract text from a PDF. pdfplumber first, PyMuPDF as fallback."""
        text = ""
        try:
            import pdfplumber
            parts = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
                    try:
                        page.flush_cache(); page.get_textmap.cache_clear()
                    except Exception:
                        pass
            text = "\n\n".join(parts)
        except Exception as e:
            logger.debug(f"pdfplumber failed: {e}")
        if len(text.strip()) < 50:
            try:
                import fitz  # PyMuPDF
                parts = []
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    for page in doc:
                        parts.append(page.get_text())
                alt = "\n\n".join(parts)
                if len(alt.strip()) > len(text.strip()):
                    text = alt
            except Exception as e:
                logger.debug(f"fitz failed: {e}")
        return text

    @staticmethod
    def _clean(text: str) -> str:
        if not text:
            return ""
        # Decode stray entities / normalise whitespace
        text = text.replace("\xa0", " ").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _inline_text(soup) -> str:
        """Pick the longest div.the-content (page renders one empty + one filled)."""
        candidates = list(soup.find_all("div", class_="the-content"))
        contenu = soup.find("div", id="contenu")
        if contenu:
            candidates.append(contenu)
        if not candidates:
            return ""
        # Strip PDF anchors so their label text doesn't pollute the body
        best = max(candidates, key=lambda d: len(d.get_text(" ", strip=True)))
        for a in best.find_all("a", href=True):
            if ".pdf" in a["href"].lower():
                a.extract()
        for tag in best.find_all(["script", "style"]):
            tag.extract()
        return best.get_text("\n", strip=True)

    @staticmethod
    def _title(soup, fallback_slug: str) -> str:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            t = og["content"]
        else:
            h1 = soup.find("h1")
            t = h1.get_text(" ", strip=True) if h1 else fallback_slug
        # Strip the site-name suffix Yoast appends
        t = re.sub(r"\s*[-–|]\s*Minist[èe]re de la Justice.*$", "", t).strip()
        return t

    @staticmethod
    def _parse_date(title: str) -> Optional[str]:
        m = _DATE_RE.search(title)
        if not m:
            return None
        day = int(m.group(1))
        month = _FR_MONTHS.get(m.group(2).lower())
        year = int(m.group(3))
        if not month:
            return None
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            return None

    @staticmethod
    def _doc_type(title: str) -> str:
        low = title.lower()
        for key in ("ordonnance", "décret", "decret", "arrêté", "arrete",
                    "loi", "code", "constitution", "convention", "accord"):
            if low.startswith(key) or low.lstrip("«\" ").startswith(key):
                return {"decret": "décret", "arrete": "arrêté"}.get(key, key)
        if "code" in low.split()[:2]:
            return "code"
        return "autre"

    # ── Enumeration ───────────────────────────────────────────────────
    def _sitemap_entries(self) -> List[Tuple[str, Optional[str]]]:
        """Return [(url, lastmod_iso_or_None), ...] from the text sitemap."""
        self.rate_limiter.wait()
        xml = self._get_html(SITEMAP_URL)
        if not xml:
            logger.error("Could not fetch sitemap")
            return []
        entries = []
        for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
            loc = re.search(r"<loc>(.*?)</loc>", block)
            mod = re.search(r"<lastmod>(.*?)</lastmod>", block)
            if loc:
                entries.append((loc.group(1).strip(),
                                mod.group(1).strip() if mod else None))
        # Fallback if <url> wrapping differs
        if not entries:
            for loc in re.findall(r"<loc>(.*?)</loc>", xml):
                entries.append((loc.strip(), None))
        logger.info(f"Sitemap: {len(entries)} text URLs")
        return entries

    def fetch_all(self) -> Generator[dict, None, None]:
        for url, lastmod in self._sitemap_entries():
            if "/texte/" in url:
                yield {"url": url, "lastmod": lastmod}

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        for url, lastmod in self._sitemap_entries():
            if "/texte/" not in url:
                continue
            if lastmod:
                try:
                    dt = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
                    if dt < since:
                        continue
                except Exception:
                    pass
            yield {"url": url, "lastmod": lastmod}

    # ── Normalisation (does the page + PDF fetch + extraction) ─────────
    def normalize(self, raw: dict) -> Optional[dict]:
        from bs4 import BeautifulSoup

        url = raw["url"]
        slug = url.rstrip("/").split("/texte/")[-1]

        html = self._get_html(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")

        title = self._title(soup, slug)
        inline = self._clean(self._inline_text(soup))

        pdf_text = ""
        pdf_url = None
        m = _PDF_RE.search(html)
        if m:
            pdf_url = m.group(0)
            pdf_bytes = self._get_pdf(pdf_url)
            if pdf_bytes:
                pdf_text = self._clean(self._pdf_text(pdf_bytes))

        if len(pdf_text) >= len(inline):
            text, text_source = pdf_text, "pdf"
        else:
            text, text_source = inline, "inline"

        if not text or len(text) < MIN_TEXT_CHARS:
            logger.debug(f"No full text ({len(text)} chars) for {slug}")
            return None

        doc_id = "KM-MoJ-" + hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
        return {
            "_id": doc_id,
            "_source": "KM/MinistryOfJustice",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": self._parse_date(title),
            "url": url,
            "doc_type": self._doc_type(title),
            "text_source": text_source,
            "pdf_url": pdf_url if text_source == "pdf" else None,
            "language": "fr",
            "slug": slug,
        }


# ── CLI ─────────────────────────────────────────────────────────────
def _run():
    scraper = KMMinistryOfJusticeScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample] [--sample-size N]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "test":
        import requests
        try:
            r = requests.get(SITEMAP_URL, headers=_HEADERS, timeout=30)
            n = len(re.findall(r"<loc>", r.text))
            print(f"Sitemap: HTTP {r.status_code}, {n} text URLs")
            ents = scraper._sitemap_entries()
            if ents:
                rec = scraper.normalize({"url": ents[4][0], "lastmod": None})
                if rec:
                    print(f"Sample doc: {rec['title'][:70]}")
                    print(f"  text={len(rec['text'])} chars, source={rec['text_source']}, date={rec['date']}")
        except Exception as e:
            print(f"Connection FAILED: {e}")
            sys.exit(1)

    elif command in ("bootstrap", "bootstrap-fast"):
        sample_mode = "--sample" in sys.argv
        sample_size = 12
        if "--sample-size" in sys.argv:
            try:
                sample_size = int(sys.argv[sys.argv.index("--sample-size") + 1])
            except (ValueError, IndexError):
                pass
        if command == "bootstrap-fast" and not sample_mode:
            stats = scraper.bootstrap_fast()
        else:
            stats = scraper.bootstrap(sample_mode=sample_mode, sample_size=sample_size)
        print("\nBootstrap complete:")
        print(f"  Records fetched: {stats['records_fetched']}")
        if sample_mode:
            print(f"  Sample records saved: {stats.get('sample_records_saved', 0)}")
        else:
            print(f"  New: {stats.get('records_new', 0)}  "
                  f"Updated: {stats.get('records_updated', 0)}  "
                  f"Skipped: {stats.get('records_skipped', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    _run()
