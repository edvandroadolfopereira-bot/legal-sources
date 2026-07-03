#!/usr/bin/env python3
"""
NO/Finanstilsynet - Norwegian Financial Supervisory Authority Doctrine Fetcher

Fetches regulatory doctrine from Finanstilsynet:
  - Rundskriv/veiledninger (circulars/guidelines) — full inline HTML text
  - Tilsynsrapporter (supervision reports) — summary + PDF full text
  - Brev (formal letters/decisions) — summary + PDF full text

Index method: XML sitemap at https://www.finanstilsynet.no/sitemap.xml
Full text: Inline HTML (rundskriv) or PDF extraction (tilsynsrapporter, brev).
License: NLOD 2.0 (Norwegian License for Open Government Data)
"""

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.finanstilsynet.no"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
SOURCE_ID = "NO/Finanstilsynet"
SAMPLE_DIR = Path(__file__).parent / "sample"
DATA_DIR = Path(__file__).parent / "data"

# Document categories we fetch (from the nyhetsarkiv)
CATEGORIES = ["rundskriv", "tilsynsrapporter", "brev"]

# Sitemap XML namespace
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _try_pdf_extract(content: bytes) -> Optional[str]:
    """Try to extract text from PDF bytes using available libraries."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            if pages:
                return "\n\n".join(pages)
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
            try:
                page.flush_cache(); page.get_textmap.cache_clear()
            except Exception:
                pass
        if pages:
            return "\n\n".join(pages)
    except Exception:
        pass

    return None


class FinanstilsynetFetcher:
    """Fetcher for Norwegian Financial Supervisory Authority documents."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Legal-Data-Hunter/1.0 (https://github.com/ZachLaik/LegalDataHunter)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5",
        })

    def fetch_sitemap_urls(self) -> Dict[str, List[str]]:
        """Parse sitemap.xml and return URLs grouped by category."""
        logger.info(f"Fetching sitemap: {SITEMAP_URL}")
        resp = self.session.get(SITEMAP_URL, timeout=60)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        urls_by_cat: Dict[str, List[str]] = {cat: [] for cat in CATEGORIES}

        for url_elem in root.findall("sm:url", NS):
            loc = url_elem.findtext("sm:loc", namespaces=NS)
            if not loc:
                continue
            for cat in CATEGORIES:
                if f"/nyhetsarkiv/{cat}/" in loc:
                    # Skip the category index page itself
                    path_after_cat = loc.split(f"/nyhetsarkiv/{cat}/")[1] if f"/nyhetsarkiv/{cat}/" in loc else ""
                    if path_after_cat and path_after_cat.strip("/"):
                        urls_by_cat[cat].append(loc)
                    break

        for cat, urls in urls_by_cat.items():
            logger.info(f"  {cat}: {len(urls)} URLs")
        return urls_by_cat

    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract main article text from a Finanstilsynet page."""
        # The main content is inside article--bodytext class area
        content = None
        for selector in [
            ("div", {"class": re.compile(r"article--bodytext")}),
            ("div", {"class": "richtext"}),
            "article",
            "main",
        ]:
            if isinstance(selector, str):
                content = soup.find(selector)
            else:
                content = soup.find(*selector)
            if content:
                break

        if not content:
            return None

        # Remove navigation, footer, sidebar, scripts, React hydration
        for tag in content.find_all(["nav", "footer", "aside", "script", "style", "noscript"]):
            tag.decompose()
        for tag in content.find_all(class_=re.compile(
            r"nav|menu|sidebar|footer|breadcrumb|cookie|banner|share|social|print-button|sr-only",
            re.I,
        )):
            tag.decompose()

        text = content.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        return text if len(text) > 100 else None

    def _extract_pdf_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract PDF download links from the page."""
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                if not href.startswith("http"):
                    href = BASE_URL + href
                pdfs.append(href)
        return pdfs

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date from meta tags or page text."""
        # Check meta tags
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").lower()
            val = tag.get("content", "")
            if val and ("published" in name or "date" in name):
                parsed = self._parse_date(val)
                if parsed:
                    return parsed

        # Check page text for Norwegian date patterns
        page_text = soup.get_text()
        for pattern in [
            r"Publisert:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
            r"Dato:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
        ]:
            m = re.search(pattern, page_text)
            if m:
                d, mo, y = m.groups()
                return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

        # Try lastmod from URL date component (e.g., /2022/...)
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """Parse date string to ISO 8601."""
        if not date_str:
            return None
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return date_str[:10]
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if m:
            d, mo, y = m.groups()
            return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _date_from_url(self, url: str) -> Optional[str]:
        """Extract year from URL path like /nyhetsarkiv/rundskriv/2022/..."""
        m = re.search(r"/nyhetsarkiv/\w+/(\d{4})/", url)
        if m:
            return f"{m.group(1)}-01-01"
        return None

    def fetch_document(self, url: str, category: str) -> Optional[Dict[str, Any]]:
        """Fetch full text and metadata from a single document page."""
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        title = None
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True).split("|")[0].strip()

        # Extract inline content
        soup2 = BeautifulSoup(resp.text, "html.parser")
        text = self._extract_content(soup2)

        # Date
        date = self._extract_date(soup) or self._date_from_url(url)

        # For tilsynsrapporter/brev with minimal inline text, try PDF extraction
        pdf_text = None
        if category in ("tilsynsrapporter", "brev") and (not text or len(text) < 2000):
            pdf_urls = self._extract_pdf_urls(soup)
            for pdf_url in pdf_urls[:2]:  # Try first 2 PDFs max
                try:
                    logger.info(f"  Downloading PDF: {pdf_url}")
                    pdf_resp = self.session.get(pdf_url, timeout=60)
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) < 50_000_000:
                        extracted = _try_pdf_extract(pdf_resp.content)
                        if extracted and len(extracted) > 200:
                            pdf_text = extracted
                            break
                    time.sleep(0.5)
                except requests.RequestException as e:
                    logger.warning(f"  PDF download failed: {e}")

        # Combine text sources
        final_text = text or ""
        if pdf_text:
            if text:
                final_text = text + "\n\n--- PDF Content ---\n\n" + pdf_text
            else:
                final_text = pdf_text

        if not final_text or len(final_text) < 100:
            logger.warning(f"No content extracted from {url}")
            return None

        return {
            "title": title or "",
            "text": final_text,
            "date": date,
            "url": url,
            "category": category,
        }

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw document into standard schema."""
        url = raw["url"]
        doc_id = hashlib.md5(url.encode()).hexdigest()[:12]

        return {
            "_id": f"NO-FT-{doc_id}",
            "_source": SOURCE_ID,
            "_type": "doctrine",
            "_fetched_at": datetime.utcnow().isoformat() + "Z",
            "title": raw.get("title", ""),
            "text": raw.get("text", ""),
            "date": raw.get("date"),
            "url": url,
            "category": raw.get("category", ""),
            "language": "nob",
        }

    def fetch_all(self) -> Iterator[Dict[str, Any]]:
        """Yield all normalized documents."""
        urls_by_cat = self.fetch_sitemap_urls()
        total = sum(len(v) for v in urls_by_cat.values())
        count = 0

        for cat in CATEGORIES:
            for url in urls_by_cat.get(cat, []):
                count += 1
                logger.info(f"[{count}/{total}] {cat}: {url}")
                doc = self.fetch_document(url, cat)
                if doc:
                    yield self.normalize(doc)
                time.sleep(1.5)

    def fetch_updates(self, since: str) -> Iterator[Dict[str, Any]]:
        """Yield documents modified since a given date (by URL year)."""
        since_year = int(since[:4])
        urls_by_cat = self.fetch_sitemap_urls()

        for cat in CATEGORIES:
            for url in urls_by_cat.get(cat, []):
                m = re.search(r"/(\d{4})/", url)
                if m and int(m.group(1)) < since_year:
                    continue
                doc = self.fetch_document(url, cat)
                if doc:
                    yield self.normalize(doc)
                time.sleep(1.5)

    def bootstrap_sample(self, n: int = 15) -> List[Dict[str, Any]]:
        """Fetch a sample of documents from each category for testing."""
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

        urls_by_cat = self.fetch_sitemap_urls()
        selected: List[tuple] = []  # (cat, url)

        # Pick samples from each category
        per_cat = max(2, n // len(CATEGORIES))
        for cat in CATEGORIES:
            cat_urls = urls_by_cat.get(cat, [])
            for url in cat_urls[:per_cat]:
                selected.append((cat, url))
            if len(selected) >= n:
                break

        # Fill remaining from largest category
        if len(selected) < n:
            for cat in sorted(CATEGORIES, key=lambda c: len(urls_by_cat.get(c, [])), reverse=True):
                for url in urls_by_cat.get(cat, [])[per_cat:]:
                    if len(selected) >= n:
                        break
                    selected.append((cat, url))
                if len(selected) >= n:
                    break

        selected = selected[:n]
        results = []

        for i, (cat, url) in enumerate(selected):
            logger.info(f"Sample {i+1}/{len(selected)} [{cat}]: {url}")
            doc = self.fetch_document(url, cat)
            if not doc:
                logger.warning(f"  Skipped (no content)")
                continue

            normalized = self.normalize(doc)
            results.append(normalized)

            fname = f"{normalized['_id']}.json"
            with open(SAMPLE_DIR / fname, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            logger.info(f"  Saved: {fname} ({len(normalized['text'])} chars)")

            time.sleep(1.5)

        logger.info(f"Sample complete: {len(results)} documents saved to {SAMPLE_DIR}")
        return results


def main():
    parser = argparse.ArgumentParser(description="NO/Finanstilsynet - Financial Supervisory Authority Fetcher")
    parser.add_argument("command", choices=["bootstrap", "bootstrap-fast", "fetch", "updates"],
                        help="Command to run")
    parser.add_argument("--sample", action="store_true",
                        help="Fetch sample data only (for bootstrap)")
    parser.add_argument("--since", type=str,
                        help="Fetch updates since date (ISO format)")
    parser.add_argument("--limit", type=int, default=15,
                        help="Max documents for sample")
    parser.add_argument("--full", action="store_true", help="Fetch all records")
    args = parser.parse_args()

    fetcher = FinanstilsynetFetcher()

    if args.command in ("bootstrap", "bootstrap-fast"):
        if args.sample:
            results = fetcher.bootstrap_sample(n=args.limit)
            print(f"\nSample: {len(results)} documents fetched")
            for r in results:
                text_len = len(r.get("text", ""))
                print(f"  {r['_id']} | {r['category']:20s} | {text_len:>6} chars | {r['title'][:60]}")
        else:
            # Full fetch — stream every record to data/records.jsonl so the
            # ingest pipeline picks up the whole corpus (not just samples).
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            jsonl_path = DATA_DIR / "records.jsonl"
            count = 0
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for doc in fetcher.fetch_all():
                    f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 50 == 0:
                        logger.info(f"Fetched {count} documents")
            print(f"Total: {count} documents written -> {jsonl_path}")

    elif args.command == "updates":
        if not args.since:
            print("Error: --since required for updates command", file=sys.stderr)
            sys.exit(1)
        count = 0
        for doc in fetcher.fetch_updates(args.since):
            count += 1
        print(f"Updates: {count} documents fetched since {args.since}")

    elif args.command == "fetch":
        count = 0
        for doc in fetcher.fetch_all():
            count += 1
        print(f"Total: {count} documents fetched")


if __name__ == "__main__":
    main()
