#!/usr/bin/env python3
"""
HT/ANJ-Repertoire -- Haiti Assemblée Nationale de la Jeunesse — Répertoire des Lois

Fetches ~40 key Haitian legal documents (constitutions, laws, decrees, codes,
historical documents) from the ANJ curated repertoire.

Strategy:
  - Scrapes the index page to discover all document links
  - Fetches each document page and extracts full text from HTML
  - Documents are organized by category (constitutions, laws, decrees, historical)

Endpoints:
  - Index: https://www.assembleenationaledelajeunesse.com/repertoire-des-lois-de-la-republique-d-haiti
  - Documents: individual HTML pages under the same path

Data:
  - ~40 documents covering 1801–2026
  - Full text embedded in HTML (no PDF extraction needed for most)
  - French language

License: Public domain (Haitian legislation)

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 10+ sample records for validation
  python bootstrap.py update             # Incremental update
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import re
import html
import io
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.HT.ANJ-Repertoire")

BASE_URL = "https://www.assembleenationaledelajeunesse.com"
INDEX_PATH = "/repertoire-des-lois-de-la-republique-d-haiti"

# Known document paths with categories (scraped from index page)
DOCUMENT_PATHS = [
    # Constitutions
    ("/repertoire-des-lois-de-la-republique-d-haiti/2595149_proposition-par-l-anj-d-avant-projet-de-constitution-de-la-republique-d-hayti", "constitution"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2595128_avant-projet-de-consititution-d-haiti-mai-2025", "constitution"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623524_constitution-de-1987-amendee", "constitution"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3174727_constitution-de-1806", "constitution"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2786353_constitution-de-1805-d-haiti-hayti", "constitution"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2809454_constitution-de-1801-de-saint-domingue-haiti", "constitution"),
    # Laws
    ("/repertoire-des-lois-de-la-republique-d-haiti/2919655_loi-portant-formation-fonctionnement-et-financement-des-partis-politiques", "loi"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623582_loi-du-1994-relative-a-la-police-nationale", "loi"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623576_loi-reformant-l-adoption-en-haiti", "loi"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623566_loi-creant-et-organisant-l-office-national-de-partenariat-en-education-onape", "loi"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623560_loi-sur-la-modernisation-des-entreprises-publiques", "loi"),
    # Decrees and codes
    ("/repertoire-des-lois-de-la-republique-d-haiti/3151771_projet-de-decret-electoral-avril-2026", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3157543_decret-regissant-les-activites-minieres-en-haiti", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2898046_decret-portant-organisation-et-fonctionnement-de-la-haute-cour-de-justice", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2792522_decret-electoral-d-haiti-octobre-2025", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623610_decret-loi-du-1er-juillet-1941-sur-la-naturalisation", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623587_decret-relatif-a-l-organisation-judiciaire-en-haiti", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2623541_decret-portant-sur-l-organisation-et-le-fonctionnement-du-mspp", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2622714_decret-portant-modalites-d-organisation-et-de-fonctionnement-de-la-collectivite-depatementale", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2622709_decret-sur-l-organisation-et-le-fonctionnement-des-sections-communales", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2612057_decret-portant-creation-organisation-et-fonctionnement-de-la-conference-nationale", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2610062_code-penal-2022", "code"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2609589_code-des-douanes", "code"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2609581_code-du-travail", "code"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2609578_code-national-du-batiment-en-haiti", "code"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2609561_code-de-l-aviation-civile", "code"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2595163_decret-portant-organisation-et-fonctionnement-de-la-collectivite-municipale", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2595159_decret-portant-cadre-general-de-la-decentralisation-organisation-et-fonctionnment-des-collectivites-territoriales-haitiennes", "decret"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2595126_decret-referendaire-de-2025", "decret"),
    # Historical documents
    ("/repertoire-des-lois-de-la-republique-d-haiti/2920014_lettre-de-toussaint-louverture-a-john-adams-le-14-aout-1799", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2795365_acte-de-soutien-des-generaux-du-nord-apres-l-assassinat-de-dessalines", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2794033_lettre-de-dessalines-a-leclerc-sur-l-arrestation-de-charles-et-sanite-belair", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2788508_resistance-a-l-oppression", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2786382_acte-d-independance-d-hayti-de-1804", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3049887_l-ordonnance-de-charles-x-du-17-avril-1825", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2934819_declaration-d-independance-du-peuple-dominicain", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3111917_passeport-delivre-par-l-empire-d-haiti-1806-10-24", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3059448_adresse-de-l-armee-d-haiti-au-general-en-chef-h-christophe", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3059438_lettre-d-etienne-gerin-au-general-henri-christophe-denoncant-le-gouvernement-de-jean-jacques-dessalines", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/3112070_decret-de-jean-jacques-dessalines-sur-le-rapatriement-des-noirs-et-indigenes-vivant-aux-etats-unis-d-amerique", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2929588_lettre-de-juste-chalante-a-thomas-jefferson", "historique"),
    ("/repertoire-des-lois-de-la-republique-d-haiti/2934849_acte-d-independance-de-saint-domingue-haiti-1803", "historique"),
]


class ANJRepertoireScraper(BaseScraper):
    """
    Scraper for HT/ANJ-Repertoire -- Haiti Répertoire des Lois.
    Country: HT
    URL: https://www.assembleenationaledelajeunesse.com

    Data types: legislation
    Auth: none (public access)
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)

        self.client = HttpClient(
            base_url=BASE_URL,
            headers={
                "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=60,
        )

    def _extract_text_from_html(self, page_html: str) -> str:
        """Extract clean text from a document page HTML."""
        # The site uses JouwWeb CMS. Content is in the news-page-content-container
        # div, ending before jw-section-footer.
        text = page_html

        # Extract the main content block
        start_idx = text.find('news-page-content-container')
        if start_idx > 0:
            # Back up to find the opening <div
            div_start = text.rfind('<div', 0, start_idx)
            if div_start > 0:
                text = text[div_start:]

        # Cut at footer
        for marker in ['jw-section-footer', 'jw-block-footer', 'class="jw-credits']:
            end_idx = text.find(marker)
            if end_idx > 0:
                text = text[:end_idx]
                break

        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Replace block elements with newlines
        text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</(?:p|div|h[1-6]|li|tr|blockquote|article|section)>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<(?:p|div|h[1-6]|li|tr|blockquote|article|section)[^>]*>', '\n', text, flags=re.IGNORECASE)

        # Strip all remaining tags
        text = self._strip_tags(text)

        # Decode HTML entities
        text = html.unescape(text)

        # Clean up whitespace — collapse multiple spaces, preserve newlines
        lines = []
        for line in text.split('\n'):
            line = re.sub(r'\s+', ' ', line).strip()
            if line:
                lines.append(line)
        text = '\n'.join(lines)

        # Remove trailing boilerplate (comments section, navigation)
        for cutoff in [
            'Ajouter un commentaire',
            'Laisser ce champ vide',
            'Il n\'y a pas encore de commentaire',
        ]:
            idx = text.find(cutoff)
            if idx > 0:
                text = text[:idx].rstrip()

        # Remove leading boilerplate (download links, PDF info)
        # Keep from the first substantive heading or paragraph
        # Remove lines like "PDF – 1,7 MB", "59 téléchargements", "Télécharger"
        cleaned_lines = []
        content_started = False
        for line in text.split('\n'):
            if not content_started:
                # Skip download/meta boilerplate at the start
                if re.match(r'^(PDF\s*[–—-]|.*téléchargement|Télécharger$|news-page-content)', line, re.IGNORECASE):
                    continue
                # Skip short navigation-like lines before content starts
                if len(line) < 10 and not re.search(r'(article|chapitre|titre|section|préambule)', line, re.IGNORECASE):
                    continue
                content_started = True
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)

        # Remove navigation arrows ("« Précédent", "Suivant »")
        text = re.sub(r'[«»]\s*(Précédent|Suivant)\s*[«»]?', '', text)
        text = re.sub(r'(Précédent|Suivant)\s*[«»]', '', text)
        text = re.sub(r'[«»]\s*(Précédent|Suivant)', '', text)

        return text.strip()

    def _strip_tags(self, html_str: str) -> str:
        """Remove all HTML tags."""
        return re.sub(r'<[^>]+>', ' ', html_str)

    def _extract_title(self, page_html: str, path: str) -> str:
        """Extract the document title from the page."""
        # Use og:title meta tag — most reliable on JouwWeb
        og_match = re.search(r'property="og:title"\s+content="([^"]+)"', page_html)
        if not og_match:
            og_match = re.search(r'content="([^"]+)"\s+property="og:title"', page_html)
        if og_match:
            title = html.unescape(og_match.group(1))
            # og:title has format "Doc Title / Section | Site Name"
            # Remove site name and section suffix
            title = re.sub(r'\s*\|\s*Assemblée.*$', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*/\s*Répertoire des Lois.*$', '', title, flags=re.IGNORECASE)
            title = title.strip()
            if title:
                return title

        # Fallback: derive from URL path
        slug = path.split('/')[-1]
        slug = re.sub(r'^\d+_', '', slug)
        return slug.replace('-', ' ').title()

    def _extract_date(self, title: str, path: str) -> str:
        """Try to extract a date from the title or URL."""
        # Look for year patterns in title
        year_match = re.search(r'\b(1[789]\d{2}|20[0-2]\d)\b', title)
        if year_match:
            return year_match.group(1)

        # Check specific date patterns: "14 août 1799", "17 avril 1825"
        date_match = re.search(
            r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})',
            title, re.IGNORECASE
        )
        if date_match:
            day, month_fr, year = date_match.groups()
            month_map = {
                'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
                'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
                'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12',
            }
            month = month_map.get(month_fr.lower(), '01')
            return f"{year}-{month}-{day.zfill(2)}"

        # Check URL for dates
        year_match = re.search(r'\b(1[789]\d{2}|20[0-2]\d)\b', path)
        if year_match:
            return year_match.group(1)

        return ""

    def _make_id(self, path: str) -> str:
        """Create a stable unique ID from the URL path."""
        slug = path.rstrip('/').split('/')[-1]
        return slug

    def _extract_pdf_urls(self, page_html: str) -> list:
        """Extract PDF download URLs from a page."""
        urls = re.findall(r'href="((?:https?://[^"]*)?_downloads/[^"]+)"', page_html)
        # Normalize relative URLs
        result = []
        for u in urls:
            if u.startswith('http'):
                result.append(u)
            elif u.startswith('/'):
                result.append(BASE_URL + u)
            else:
                result.append(BASE_URL + '/' + u.lstrip('./'))
        # Deduplicate preserving order
        seen = set()
        deduped = []
        for u in result:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download a PDF and extract its text."""
        if not HAS_PDFPLUMBER:
            logger.debug("pdfplumber not available for PDF extraction")
            return ""
        try:
            self.rate_limiter.wait()
            resp = self.client.get(pdf_url.replace(BASE_URL, ''))
            if resp.status_code != 200:
                return ""
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            pdf.close()
            return '\n'.join(pages_text)
        except Exception as e:
            logger.debug(f"PDF extraction failed: {e}")
            return ""

    def fetch_all(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch all documents with full text from HTML pages or PDFs."""
        logger.info(f"Fetching {len(DOCUMENT_PATHS)} documents from ANJ Répertoire")

        for path, category in DOCUMENT_PATHS:
            doc_id = self._make_id(path)
            url = BASE_URL + path

            self.rate_limiter.wait()
            try:
                resp = self.client.get(path)
            except Exception as e:
                logger.warning(f"Failed to fetch {doc_id}: {e}")
                continue

            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {doc_id}")
                continue

            page_html = resp.text
            title = self._extract_title(page_html, path)
            text = self._extract_text_from_html(page_html)
            date = self._extract_date(title, path)

            # If inline text is too short, try PDF extraction
            if len(text.strip()) < 500:
                pdf_urls = self._extract_pdf_urls(page_html)
                for pdf_url in pdf_urls:
                    pdf_text = self._extract_pdf_text(pdf_url)
                    if len(pdf_text) > len(text):
                        text = pdf_text
                        logger.info(f"  Used PDF fallback for {doc_id} ({len(text)} chars)")
                        break

            if not text or len(text.strip()) < 500:
                logger.warning(f"Skipping {doc_id} — insufficient text ({len(text)} chars, likely scanned PDF)")
                continue

            yield self.normalize({
                "_id": doc_id,
                "title": title,
                "text": text,
                "date": date,
                "url": url,
                "category": category,
            })

    def fetch_updates(self, since: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """Fetch updates — re-fetches all (small corpus)."""
        yield from self.fetch_all()

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw document data into standard schema."""
        cat = raw.get("category", "")
        if cat in ("constitution", "loi"):
            doc_type = "constitution" if cat == "constitution" else "loi"
        elif cat == "code":
            doc_type = "code"
        elif cat == "decret":
            doc_type = "décret"
        elif cat == "historique":
            doc_type = "document historique"
        else:
            doc_type = cat

        return {
            "_id": raw["_id"],
            "_source": "HT/ANJ-Repertoire",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "date": raw.get("date", ""),
            "url": raw.get("url", ""),
            "category": raw.get("category", ""),
            "document_type": doc_type,
            "language": "fr",
        }

    def test_connection(self) -> bool:
        """Test connectivity to the ANJ website."""
        try:
            resp = self.client.get(INDEX_PATH)
            return resp.status_code == 200
        except Exception:
            return False


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="HT/ANJ-Repertoire Haitian Legislation Scraper")
    parser.add_argument(
        "command",
        choices=["bootstrap", "bootstrap-fast", "update", "test"],
        help="Command to run",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Only fetch a sample of records (for validation)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch all records (default for bootstrap)",
    )

    args = parser.parse_args()
    scraper = ANJRepertoireScraper()

    if args.command == "test":
        if scraper.test_connection():
            print("OK — Connection successful")
            sys.exit(0)
        else:
            print("FAIL — Could not connect")
            sys.exit(1)

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        count = 0
        max_records = 15 if args.sample else 999999

        for record in scraper.fetch_all():
            count += 1
            fname = re.sub(r'[^\w\-]', '_', record["_id"])[:80]
            sample_path = sample_dir / f"{fname}.json"
            with open(sample_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            text_len = len(record.get("text", ""))
            logger.info(f"[{count}] {record['_id']} — {text_len} chars")

            if count >= max_records:
                break

        print(f"\nDone: {count} records saved to {sample_dir}")
        return

    if args.command == "update":
        count = 0
        for record in scraper.fetch_updates():
            count += 1
            logger.info(f"[{count}] {record['_id']}")
        print(f"Update complete: {count} records")


if __name__ == "__main__":
    main()
