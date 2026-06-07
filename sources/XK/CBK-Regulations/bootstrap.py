#!/usr/bin/env python3
"""
XK/CBK-Regulations — Central Bank of the Republic of Kosovo

Fetches banking regulations, laws, and instructions from bqk-kos.org.
The site's HTML pages are behind Cloudflare JS challenge, but PDFs under
/wp-content/uploads/ are directly accessible. We discover PDF links from
Wayback Machine cached category pages, supplemented by a seed list of
known regulation URLs found via web search.

Full text is extracted from PDFs via common.pdf_extract.

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap --sample
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, List, Dict, Any, Set
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient
from common.pdf_extract import extract_pdf_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.XK.CBK-Regulations")

BASE_URL = "https://bqk-kos.org"
DELAY = 2.0

# Wayback Machine cached category pages (English) that list regulation PDFs.
# The live pages are behind Cloudflare; Wayback snapshots bypass this.
WAYBACK_CATEGORY_URLS = [
    "https://web.archive.org/web/2024/https://bqk-kos.org/legal-framework/regulations/banks/?lang=en",
    "https://web.archive.org/web/2024/https://bqk-kos.org/legal-framework/regulations/banking-operations-2/?lang=en",
    "https://web.archive.org/web/2024/https://bqk-kos.org/legal-framework/regulations/insurance/?lang=en",
    "https://web.archive.org/web/2024/https://bqk-kos.org/legal-framework/regulations/pensions/?lang=en",
    "https://web.archive.org/web/2024/https://bqk-kos.org/legal-framework/laws/?lang=en",
]

# Seed list of known regulation/law PDF URLs discovered via web search.
# These are directly accessible on bqk-kos.org (bypass Cloudflare).
SEED_PDFS = [
    # Banks
    "https://bqk-kos.org/wp-content/uploads/2024/11/ENG-Rregullorja-per-Ekspozimet-e-Medha.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/ENG-Rregullore-per-operacionet-me-para.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/ENG-Final-Draft-Regulation-on-Factoring-180918.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/ENG-Rregullore-RLlB-1-1.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/ENG-Rregullore-per-PPP-LFT-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/Regulation-on-Credit-Risk-Management-28.03.2019.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/International-Payments.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/2015_09_14-Draft-regulation-on-ELA-3.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/11/Law-on-Banks-MFI.pdf",
    # Payment services
    "https://bqk-kos.org/wp-content/uploads/2024/12/13_REGULATION-ON-TECHNICAL-STANDARDS-FOR-SCA-AND-COMMON-AND-SECURE-OPEN-STANDARDS-OF-COMMUNICATION.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/12/Rregullore-per-operacionet-me-para-te-gatshme-1-anglisht-2.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/12/8_RREGULLORE-PER-KONTABILITETIN-DHE-AUDITIMIN-E-JASHTEM-TE-IP-DHE-IPE.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/12/Instructions-on-reporting_LCR.pdf",
    # Insurance
    "https://bqk-kos.org/wp-content/uploads/2021/04/ENG-Rregullore-Sigurime-30-05-2019.pdf",
    "https://bqk-kos.org/wp-content/uploads/2021/04/ENG-Rregullore-per-Bashkimet-dhe-Pervetesimet_0001.pdf",
    "https://bqk-kos.org/wp-content/uploads/2021/04/ENG-Rregullore-per-strukturen-e-primit-per-sigurime.pdf",
    "https://bqk-kos.org/wp-content/uploads/2021/04/ENG-Standardet-e-Raportimit-dhe-te-Mbikeqyrjes-se-Byrose-1.pdf",
    "https://bqk-kos.org/wp-content/uploads/2021/04/ENG-Kushtet-e-pergjitheshme-te-Polices-se-Sigurimit-nga-Autopergjegjesia.pdf",
    "https://bqk-kos.org/wp-content/uploads/2021/12/FINAL-Rregullore-per-Delegimin-e-Funksioneve-te-Siguruesit-verizoni-final-ANG-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2023/09/ENG-Rregullore-per-menaxhimin-e-komisioneve-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/05/ENG-Rregullore-per-Kerkesat-e-Mbajtjes-se-Rrezikut-finale-1.pdf",
    # Pensions
    "https://bqk-kos.org/wp-content/uploads/2021/11/ENG-Rregullore-per-raportim-te-FKPK-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2022/02/ENG-Rregullore-per-Transferet-dhe-Pagesat-FP2022.pdf",
    "https://bqk-kos.org/wp-content/uploads/2022/02/ENG-Rregullore-per-percaktimin-e-perfituesve-te-pensionit2022.pdf",
    "https://bqk-kos.org/wp-content/uploads/2022/07/ENG-5.-Rregullore-per-Auditimin-e-Jashtem-te-Fondeve-Pensionale2022.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/03/ENG-Rregullore-per-Sistemet-dhe-Sigurine-e-Informacionit.pdf",
    # NBFI
    "https://bqk-kos.org/wp-content/uploads/2021/05/ENG-5.-Rregullore-per-regjistrimin-e-institucioneve-financiare-jobankare.pdf",
    "https://bqk-kos.org/wp-content/uploads/2024/10/Rregullore-per-Normen-Efektive-te-interesit-per-IFJB.pdf",
    # Information systems / cyber
    "https://bqk-kos.org/wp-content/uploads/2025/09/ENG-Rregullore-per-sistemet-e-informacionit-1-1.pdf",
    "https://bqk-kos.org/wp-content/uploads/2025/09/Rregullore-per-sistemet-e-informacionit-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2025/09/Rregullore-per-platformen-per-krahasimin-e-produkteve.pdf",
    # Laws
    "https://bqk-kos.org/wp-content/uploads/2026/04/LIGJI_NR.08_L-295_PER_KRIPTO-ASETET.pdf",
    "https://bqk-kos.org/wp-content/uploads/2025/12/Rregullore-per-informacionet-e-transfereve-finale.pdf",
    # More banks (from Wayback)
    "https://bqk-kos.org/wp-content/uploads/2023/01/ENG-Rregullore-per-qasje-ne-llogari-pagese-me-sherbime-bazike-.pdf",
    "https://bqk-kos.org/wp-content/uploads/2023/03/ENG-Rregullore-per-Raportimin-e-Bankave.pdf",
    "https://bqk-kos.org/wp-content/uploads/2023/04/ENG-Rregullore-Menaxhimi-Rreziku-Likuiditeti.pdf",
    "https://bqk-kos.org/wp-content/uploads/2023/01/ENG-Rregullore-per-Menaxhimin-e-Rrezikut-te-Normes-se-Interesit-ne-Librin.pdf",
    # Complaint handling
    "https://bqk-kos.org/wp-content/uploads/2024/12/16_RREGULLORE-PER-PROCESIN-E-TRAJTIMIT-TE-ANKESAVE-NGA-INSTITUCIONET-FINANCIARE.pdf",
    # Mortgage
    "https://bqk-kos.org/wp-content/uploads/2024/11/Rregullore-per-Kredite-Hipotekare-.pdf",
    # Standard account numbering
    "https://bqk-kos.org/wp-content/uploads/2024/11/Sistemi-i-Numrave-Standard-te-Llogarive-Bankare.pdf",
]

# Patterns that indicate a PDF is a regulation/law/instruction (not a report/stats)
REGULATION_PATTERNS = re.compile(
    r"rregullore|regulation|law-on|ligji|instruction|kushtet|standardet|"
    r"ENG-.*rregull|REGULATION|draft-regulation|credit-risk|factoring|"
    r"international-payment|reporting-instruction|ELA-",
    re.I,
)

# Patterns for non-regulation documents (financial reports, statistics, etc.)
EXCLUDE_PATTERNS = re.compile(
    r"CBK_BLSK|CBK_FS_|CBK_MSB|CBK_QAE|FS_\d|financial-system|"
    r"Financial-Statements|BQK_BMS|BQK_TM|Auction-Announcement|"
    r"Pasqyra-e-gjendjes|Pregled-finansijskog|statement-of-financial|"
    r"Monthly-Report|BQK_AKB|BQK_Ngarkesa|sistemi-financiar|"
    r"ENG-Final_Financial|bonus-malus|Norma-e-interesit-ENG-PDF|"
    r"Lista-e-institucioneve|Manuali|Pyetjet-e-shpeshta|FAQ-Regulation|"
    r"Minutat-e-takimit|ENG-Minutat|BQK-RV|BQK_RV|CBK_GI|"
    r"Godisnji-Izvjestaj|GI_\d",
    re.I,
)


def _is_regulation_pdf(url: str) -> bool:
    """Check if a URL looks like a regulation/law PDF rather than a report."""
    filename = unquote(url).split("/")[-1]
    if EXCLUDE_PATTERNS.search(filename):
        return False
    if REGULATION_PATTERNS.search(filename):
        return True
    # Accept any PDF from the uploads dir that doesn't match exclude patterns
    # since many regulations have Albanian names we might not pattern-match
    return True


def _make_id(pdf_url: str) -> str:
    """Generate a stable ID from the PDF filename."""
    name = unquote(pdf_url).split("/")[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")
    if len(name) > 80:
        name = name[:80]
    return f"XK_CBK_{name}"


def _extract_date_from_path(pdf_url: str) -> Optional[str]:
    """Try to extract a date from the wp-content/uploads path (YYYY/MM pattern)."""
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", pdf_url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return None


def _clean_title(filename: str) -> str:
    """Generate a readable title from the PDF filename."""
    name = unquote(filename)
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"^(ENG-|ANGL-|FINAL-)", "", name)
    name = re.sub(r"^\d+[._]\s*", "", name)  # Remove leading numbers
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


class CBKScraper(BaseScraper):
    """Scraper for Kosovo Central Bank regulations."""

    def __init__(self):
        source_dir = Path(__file__).resolve().parent
        super().__init__(str(source_dir))
        self.http = HttpClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

    def _discover_from_wayback(self) -> Set[str]:
        """Discover regulation PDF URLs from Wayback Machine cached pages."""
        pdf_urls: Set[str] = set()
        for wb_url in WAYBACK_CATEGORY_URLS:
            try:
                logger.info("Fetching Wayback page: %s", wb_url[:80])
                resp = self.http.get(wb_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning("Wayback HTTP %d for %s", resp.status_code, wb_url[:80])
                    continue
                # Extract PDF links from Wayback-archived page
                for m in re.finditer(
                    r'href="(?:https://web\.archive\.org/web/\d+/)?'
                    r'(https://bqk-kos\.org/wp-content/uploads/[^"]+\.pdf)[^"]*"',
                    resp.text, re.I,
                ):
                    url = m.group(1)
                    # Remove ?lang=en query params from the stored URL
                    url = re.sub(r"\?.*$", "", url)
                    if _is_regulation_pdf(url):
                        pdf_urls.add(url)
                time.sleep(1)
            except Exception as e:
                logger.warning("Wayback fetch failed for %s: %s", wb_url[:60], e)
        logger.info("Discovered %d regulation PDFs from Wayback Machine", len(pdf_urls))
        return pdf_urls

    def _get_all_pdf_urls(self) -> List[str]:
        """Combine Wayback discovery with seed list, deduplicate."""
        # Start with seed list
        all_urls: Set[str] = set()
        for url in SEED_PDFS:
            clean = re.sub(r"\?.*$", "", url)
            if _is_regulation_pdf(clean):
                all_urls.add(clean)

        # Add Wayback discoveries
        wayback_urls = self._discover_from_wayback()
        all_urls.update(wayback_urls)

        logger.info("Total unique regulation PDF URLs: %d", len(all_urls))
        return sorted(all_urls)

    def _download_and_extract(self, pdf_url: str, doc_id: str) -> Optional[str]:
        """Download a PDF and extract text."""
        try:
            resp = self.http.get(pdf_url, timeout=60)
            if resp.status_code == 404:
                logger.info("PDF not found (404), skipping: %s", pdf_url.split("/")[-1])
                return None
            if resp.status_code != 200:
                logger.warning("HTTP %d downloading %s", resp.status_code, pdf_url)
                return None
            pdf_bytes = resp.content
            if len(pdf_bytes) < 500:
                logger.warning("PDF too small (%d bytes): %s", len(pdf_bytes), pdf_url)
                return None
            text = extract_pdf_markdown("XK/CBK-Regulations", doc_id, pdf_bytes=pdf_bytes)
            return text
        except Exception as e:
            logger.warning("Failed to download/extract %s: %s", pdf_url.split("/")[-1], e)
            return None

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all CBK regulation documents with full text from PDFs."""
        pdf_urls = self._get_all_pdf_urls()
        logger.info("Processing %d regulation PDFs", len(pdf_urls))

        for pdf_url in pdf_urls:
            filename = unquote(pdf_url).split("/")[-1]
            doc_id = _make_id(pdf_url)
            logger.info("Processing: %s", filename[:80])

            text = self._download_and_extract(pdf_url, doc_id)
            if not text or len(text.strip()) < 100:
                logger.warning("Insufficient text for %s, skipping", filename[:60])
                continue

            title = _clean_title(filename)
            date = _extract_date_from_path(pdf_url)

            yield {
                "_id": doc_id,
                "title": title,
                "date": date,
                "pdf_url": pdf_url,
                "text": text,
            }
            time.sleep(DELAY)

    def fetch_updates(self, since: str = "") -> Generator[dict, None, None]:
        """Fetch updates — for a small static collection, re-fetch all."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Transform raw document into standard schema."""
        return {
            "_id": raw["_id"],
            "_source": "XK/CBK-Regulations",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date"),
            "url": raw.get("pdf_url", ""),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="XK/CBK-Regulations bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Run full bootstrap")
    boot.add_argument("--sample", action="store_true", help="Fetch sample only")
    boot.add_argument("--sample-size", type=int, default=15, help="Sample size")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    sub.add_parser("bootstrap-fast", help="Quick sample (alias for bootstrap --sample)")
    sub.add_parser("test", help="Quick connectivity test")

    args = parser.parse_args()
    scraper = CBKScraper()

    if args.command == "test":
        # Test direct PDF access (bypasses Cloudflare)
        test_url = SEED_PDFS[0]
        resp = scraper.http.get(test_url, timeout=15)
        print(f"PDF access test: HTTP {resp.status_code} ({len(resp.content)} bytes)")
        if resp.status_code == 200:
            print("OK — PDFs are accessible (Cloudflare bypassed)")
        else:
            print("FAIL — PDFs not accessible")
        return

    if args.command == "bootstrap-fast":
        stats = scraper.bootstrap(sample_mode=True, sample_size=15)
        print(json.dumps(stats, indent=2))
    elif args.command == "bootstrap":
        sample = args.sample and not args.full
        stats = scraper.bootstrap(sample_mode=sample, sample_size=args.sample_size)
        print(json.dumps(stats, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
