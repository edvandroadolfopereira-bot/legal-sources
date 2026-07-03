#!/usr/bin/env python3
"""
CO/GestorNormativo -- Colombia Gestor Normativo (Función Pública) Fetcher

Fetches full text of Colombian norms from Función Pública's Gestor Normativo.

Strategy:
  - Use search API to enumerate norm IDs by document type
  - For each norm ID, fetch norma.php?i={id} and extract full text
  - Clean HTML, decode entities, strip CSS/JS artifacts

Usage:
  python bootstrap.py bootstrap          # Full initial pull
  python bootstrap.py bootstrap --sample # Fetch 15 sample records
  python bootstrap.py bootstrap-fast     # Alias for bootstrap
  python bootstrap.py test               # Quick connectivity test
"""

import sys
import json
import logging
import time
import re
import html as html_module
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.CO.GestorNormativo")

BASE_URL = "https://www.funcionpublica.gov.co/eva/gestornormativo"
SEARCH_URL = f"{BASE_URL}/gestion/funphp/funajax.php"

# Document type IDs from the advanced search dropdown
# Focus on legislation-relevant types for bootstrap
DOC_TYPES = {
    18: "Ley",
    11: "Decreto",
    986: "Decreto Ley",
    2: "Acto Legislativo",
    29: "Resolución",
    8: "Constitución Política",
    30: "Sentencia",
    925: "Concepto Sala de Consulta C.E.",
    6: "Circular",
    13: "Directiva",
    3: "Acuerdo",
    987: "Decretos Salariales",
    7: "Concepto",
    1205: "Auto",
    825: "Circular Externa",
    184: "Circular Conjunta",
    985: "Documento CONPES",
    905: "Estatutos",
    989: "Reglamento",
    988: "Criterio Unificado",
    785: "Concepto Marco",
    14: "Documento de Relatoria",
    845: "Circular Unificada",
    1185: "Comunicado",
    1245: "Circular Vicepresidencial",
    1225: "Directiva Vicepresidencial",
    1285: "Directiva Presidencial",
    1305: "Conceptos Guias",
}

# Priority types for sample/bootstrap (most important first)
PRIORITY_TYPES = [18, 11, 986, 2, 29, 8, 30, 925]


class GestorNormativoScraper(BaseScraper):
    """Scraper for CO/GestorNormativo — Colombian norms from Función Pública."""

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        try:
            from common.http_client import HttpClient
            self.client = HttpClient(timeout=30)
        except ImportError:
            self.client = None

    def _http_get(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        """HTTP GET returning response text."""
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        if headers:
            default_headers.update(headers)

        for attempt in range(3):
            try:
                if self.client:
                    resp = self.client.get(url, headers=default_headers)
                    if resp.status_code == 200 and len(resp.text) > 10:
                        return resp.text
                    if resp.status_code in (404, 500):
                        return None
                else:
                    import urllib.request
                    req = urllib.request.Request(url, headers=default_headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read().decode("utf-8", errors="replace")
                        if len(data) > 10:
                            return data
                        return None
            except Exception as e:
                logger.debug(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        return None

    def _get_norm_ids_for_type(self, type_id: int) -> List[str]:
        """Get all norm IDs for a given document type via search API."""
        url = (f"{SEARCH_URL}?t=ejecuta_busqueda_avanzada2"
               f"&tipdoc={type_id}&pagina=1")
        headers = {
            "Referer": f"{BASE_URL}/consulta_avanzada.php",
        }
        text = self._http_get(url, headers=headers)
        if not text:
            return []

        ids = re.findall(r'norma\.php\?i=(\d+)', text)
        return list(dict.fromkeys(ids))  # deduplicate preserving order

    def _parse_norm_page(self, norm_id: str, raw_html: str) -> Optional[Dict[str, Any]]:
        """Parse a norm page and extract structured data."""
        # Title
        title_m = re.search(
            r'titulo-norma[^>]*><strong>(.*?)</strong>', raw_html, re.DOTALL
        )
        title = html_module.unescape(title_m.group(1).strip()) if title_m else None
        if not title:
            return None

        # Date from meta
        date_m = re.search(r'dateModified"\s+content="([^"]+)"', raw_html)
        date_str = date_m.group(1) if date_m else None

        # Description from og:description
        desc_m = re.search(r'og:description"\s+content="([^"]+)"', raw_html)
        description = html_module.unescape(desc_m.group(1).strip()) if desc_m else ""

        # Extract text from descripcion-contenido div
        text = self._extract_content_text(raw_html)
        if not text or len(text) < 50:
            return None

        # Infer norm type from title
        norm_type = self._infer_type(title)

        return {
            "norm_id": norm_id,
            "title": title,
            "text": text,
            "norm_type": norm_type,
            "date": date_str,
            "description": description,
        }

    def _extract_content_text(self, raw_html: str) -> Optional[str]:
        """Extract and clean text from the descripcion-contenido div."""
        marker = '<div class="descripcion-contenido">'
        pos = raw_html.find(marker)
        if pos == -1:
            return None

        start = pos + len(marker)
        # Find matching closing div by tracking depth
        depth = 1
        i = start
        end = len(raw_html)
        while depth > 0 and i < end:
            next_open = raw_html.find("<div", i)
            next_close = raw_html.find("</div>", i)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                i = next_open + 4
            else:
                depth -= 1
                if depth == 0:
                    content = raw_html[start:next_close]
                    break
                i = next_close + 6
        else:
            content = raw_html[start:start + 200000]

        # Remove style and script blocks
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)

        # Convert br tags to newlines
        content = re.sub(r'<br\s*/?>', '\n', content)

        # Strip all HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)

        # Decode HTML entities
        content = html_module.unescape(content)

        # Clean whitespace
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n[ \t]+', '\n', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()

        # Remove CSS artifacts that may leak through
        if content.startswith(('@font-face', 'body {', ':root{')):
            # CSS leaked — try to find actual text after it
            # Look for common norm text patterns
            for pattern in [r'(?:LEY|DECRETO|SENTENCIA|RESOLUCIÓN|ACUERDO)',
                            r'(?:ARTÍCULO|ARTICULO)\s+\d+']:
                m = re.search(pattern, content, re.IGNORECASE)
                if m:
                    content = content[m.start():]
                    break

        return content if len(content) >= 50 else None

    def _infer_type(self, title: str) -> str:
        """Infer document type from title."""
        title_lower = title.lower()
        for keyword, dtype in [
            ("ley ", "Ley"), ("decreto ley", "Decreto Ley"),
            ("decreto", "Decreto"), ("sentencia", "Sentencia"),
            ("resolución", "Resolución"), ("resolucion", "Resolución"),
            ("acto legislativo", "Acto Legislativo"),
            ("concepto", "Concepto"), ("circular", "Circular"),
            ("acuerdo", "Acuerdo"), ("constitución", "Constitución"),
            ("auto ", "Auto"), ("directiva", "Directiva"),
        ]:
            if keyword in title_lower:
                return dtype
        return "Otro"

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw data into standard schema."""
        norm_id = raw["norm_id"]
        return {
            "_id": f"CO-GestorNormativo-{norm_id}",
            "_source": "CO/GestorNormativo",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": raw["title"],
            "text": raw["text"],
            "norm_type": raw.get("norm_type", ""),
            "date": raw.get("date"),
            "description": raw.get("description", ""),
            "url": f"{BASE_URL}/norma.php?i={norm_id}",
            "norm_id": norm_id,
        }

    def fetch_all(self, sample: bool = False) -> Generator[Dict[str, Any], None, None]:
        """Fetch all norms. If sample=True, fetch ~15 from priority types."""
        if sample:
            yield from self._fetch_sample()
            return

        # Full fetch: enumerate all types
        for type_id in DOC_TYPES:
            type_name = DOC_TYPES[type_id]
            logger.info(f"Fetching norm IDs for type: {type_name} (id={type_id})")
            ids = self._get_norm_ids_for_type(type_id)
            logger.info(f"  Found {len(ids)} norms of type {type_name}")
            time.sleep(1)

            for norm_id in ids:
                record = self._fetch_single_norm(norm_id)
                if record:
                    yield record
                time.sleep(1.5)

    def _fetch_sample(self) -> Generator[Dict[str, Any], None, None]:
        """Fetch ~15 sample records from priority document types."""
        count = 0
        target = 15

        for type_id in PRIORITY_TYPES:
            if count >= target:
                break
            type_name = DOC_TYPES[type_id]
            logger.info(f"Fetching sample IDs for type: {type_name}")
            ids = self._get_norm_ids_for_type(type_id)
            if not ids:
                continue
            time.sleep(1)

            # Take first 3 from each type
            for norm_id in ids[:3]:
                if count >= target:
                    break
                record = self._fetch_single_norm(norm_id)
                if record:
                    yield record
                    count += 1
                time.sleep(1.5)

    def _fetch_single_norm(self, norm_id: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single norm page."""
        url = f"{BASE_URL}/norma.php?i={norm_id}"
        logger.info(f"Fetching norm {norm_id}...")
        raw_html = self._http_get(url)
        if not raw_html or len(raw_html) < 100:
            logger.warning(f"Empty/unavailable page for norm {norm_id}")
            return None

        parsed = self._parse_norm_page(norm_id, raw_html)
        if not parsed:
            logger.warning(f"Could not parse norm {norm_id}")
            return None

        normalized = self.normalize(parsed)
        text_len = len(normalized.get("text", ""))
        logger.info(f"  → {normalized['title']} ({text_len} chars)")
        return normalized

    def fetch_updates(self, since: str) -> Generator[Dict[str, Any], None, None]:
        """Fetch norms modified since a date (not implemented for HTML scraping)."""
        logger.warning("fetch_updates not supported; use fetch_all")
        return
        yield

    def test_connection(self) -> bool:
        """Quick connectivity test."""
        text = self._http_get(f"{BASE_URL}/norma.php?i=300")
        if text and "Ley 87 de 1993" in text:
            logger.info("Connection test passed — Ley 87 de 1993 accessible")
            return True
        logger.error("Connection test failed")
        return False


def main():
    scraper = GestorNormativoScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|bootstrap-fast|test] [--sample] [--full]")
        sys.exit(1)

    command = sys.argv[1]
    sample = "--sample" in sys.argv
    full = "--full" in sys.argv

    if command == "test":
        ok = scraper.test_connection()
        sys.exit(0 if ok else 1)

    if command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        sample_dir.mkdir(exist_ok=True)

        use_sample = sample and not full
        records = []
        for record in scraper.fetch_all(sample=use_sample):
            records.append(record)
            # Save each record
            fname = f"{record['_id']}.json"
            fname = re.sub(r'[^\w\-.]', '_', fname)
            with open(sample_dir / fname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

        logger.info(f"Total records fetched: {len(records)}")

        # Validate
        texts = [r for r in records if r.get("text") and len(r["text"]) > 50]
        logger.info(f"Records with full text: {len(texts)}/{len(records)}")

        if records:
            avg_len = sum(len(r.get("text", "")) for r in records) / len(records)
            logger.info(f"Average text length: {avg_len:.0f} chars")

        sys.exit(0)

    print(f"Unknown command: {command}")
    sys.exit(1)


if __name__ == "__main__":
    main()
