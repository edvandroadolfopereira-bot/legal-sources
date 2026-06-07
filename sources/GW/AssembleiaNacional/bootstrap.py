#!/usr/bin/env python3
"""
Guinea-Bissau National People's Assembly (Assembleia Nacional Popular) Data Fetcher

Crawls the Plone CMS portal at parlamento.gw to extract legislation full text.
Categories: constitution, legislation, statutes/bylaws, treaties.
Full text available in HTML for most documents; PDF fallback where needed.

Data source: https://www.parlamento.gw/leis
License: Public domain (government legislation)
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

SOURCE_ID = "GW/AssembleiaNacional"
BASE_URL = "https://www.parlamento.gw"
LAWS_URL = f"{BASE_URL}/leis"
REQUEST_DELAY = 2.0

# Categories to crawl and their URL paths
CATEGORIES = [
    ("constituicao", "Constitution"),
    ("legislacao", "Legislation"),
    ("estatutos-e-regimentos", "Statutes & Bylaws"),
    ("tratados-e-acordos-internacionais", "Treaties & International Agreements"),
    ("leis-federais", "Autarchic Laws"),
]

# Known documents with confirmed full text availability.
# (url, title, category, source_type)  source_type: "html" or "pdf"
KNOWN_DOCUMENTS = [
    ("/leis/constituicao/constituicao-da-republica",
     "Constituição da República da Guiné-Bissau", "Constitution", "html"),
    ("/leis/legislacao/lei-da-cidadania",
     "Lei da Cidadania (Lei N.º 2/92)", "Legislation", "html"),
    ("/leis/legislacao/lei-do-recenseamento-eleitoral",
     "Lei do Recenseamento Eleitoral (Lei N.º 2/98)", "Legislation", "html"),
    ("/leis/legislacao/lei-da-observacao-internacional-eleitoral",
     "Lei da Observação Internacional Eleitoral", "Legislation", "html"),
    ("/leis/legislacao/lei-quadro-dos-partidos-politicos",
     "Lei Quadro dos Partidos Políticos", "Legislation", "html"),
    ("/leis/estatutos-e-regimentos/estatutos-dos-deputados-1/estatuto-dos-deputados.pdf",
     "Estatuto dos Deputados (1996)", "Statutes & Bylaws", "pdf"),
    ("/leis/tratados-e-acordos-internacionais/lista-dos-tratados-e-convencoes",
     "Lista dos Tratados e Convenções Internacionais", "Treaties", "html"),
    ("/leis/tratados-e-acordos-internacionais/declaracao-de-bissau",
     "Declaração de Bissau (2015)", "Treaties", "html"),
    ("/leis/tratados-e-acordos-internacionais/atos-assinados-entre-portugal-e-guine-bissau",
     "Actos Assinados entre Portugal e Guiné-Bissau", "Treaties", "html"),
    ("/leis/estatutos-e-regimentos/regimento-interno/regimento-da-assembleia-nacional-popular",
     "Regimento da Assembleia Nacional Popular", "Statutes & Bylaws", "html"),
]


def curl_get(url: str, timeout: int = 30, accept: str = "text/html", retries: int = 2) -> Optional[str]:
    """Fetch URL content using curl with retries."""
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ['curl', '-sL', '--compressed', '--max-time', str(timeout),
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-H', f'Accept: {accept}',
                 url],
                capture_output=True, text=True, timeout=timeout + 10
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"  curl error for {url}: {e}")
        if attempt < retries:
            time.sleep(2)
    return None


def curl_get_binary(url: str, timeout: int = 60) -> Optional[bytes]:
    """Fetch binary content using curl."""
    try:
        result = subprocess.run(
            ['curl', '-sL', '--compressed', '--max-time', str(timeout),
             '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
             url],
            capture_output=True, timeout=timeout + 10
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
        return None
    except Exception as e:
        print(f"  curl binary error for {url}: {e}")
        return None


def clean_html(html_text: str) -> str:
    """Strip HTML tags and clean text."""
    if not html_text:
        return ""
    text = unescape(html_text)
    # Convert block elements to newlines
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</?p[^>]*>', '\n', text)
    text = re.sub(r'</?li[^>]*>', '\n- ', text)
    text = re.sub(r'</?(?:ul|ol)[^>]*>', '\n', text)
    text = re.sub(r'</?h[1-6][^>]*>', '\n', text)
    text = re.sub(r'</?(?:div|section|article|blockquote|pre)[^>]*>', '\n', text)
    text = re.sub(r'</?tr[^>]*>', '\n', text)
    text = re.sub(r'</?t[dh][^>]*>', ' | ', text)
    # Remove style/script blocks
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


def extract_content_from_html(html: str) -> str:
    """Extract main content from a Plone page HTML."""
    # Try to find #content-core or #parent-fieldname-text
    patterns = [
        r'<div[^>]*id="parent-fieldname-text"[^>]*>(.*?)</div>\s*(?:</div>|<div[^>]*id=)',
        r'<div[^>]*id="content-core"[^>]*>(.*?)</div>\s*(?:<div[^>]*id="viewlet|<footer|</article)',
        r'<article[^>]*>(.*?)</article>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1)
            text = clean_html(content)
            if len(text) > 100:
                return text

    # Fallback: extract everything between #content and #portal-footer
    match = re.search(
        r'<div[^>]*id="content"[^>]*>(.*?)<(?:div[^>]*id="(?:portal-footer|viewlet-below)|footer)',
        html, re.DOTALL | re.IGNORECASE
    )
    if match:
        text = clean_html(match.group(1))
        # Remove navigation/breadcrumb noise
        lines = text.split('\n')
        content_lines = []
        skip_nav = True
        for line in lines:
            stripped = line.strip()
            if skip_nav and (not stripped or stripped in ('Página Inicial', 'Leis', 'Constituição',
                'Legislação', 'Estatutos e Regimentos', 'Tratados e Acordos Internacionais',
                'Leis Autárquicas') or stripped.startswith('Você está aqui')):
                continue
            skip_nav = False
            content_lines.append(line)
        text = '\n'.join(content_lines).strip()
        if len(text) > 100:
            return text

    return ""


def extract_links_from_category(html: str, category_url: str) -> List[Tuple[str, str]]:
    """Extract document links from a category listing page."""
    links = []
    cat_path = category_url.replace(BASE_URL, '').rstrip('/')

    # Find all <a> tags with href
    for match in re.finditer(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL):
        href = match.group(1)
        link_text = clean_html(match.group(2)).strip()

        # Skip empty, very short, or navigation-like link text
        if not link_text or len(link_text) < 3:
            continue
        # Skip known navigation noise
        noise = {'TV da ANP', 'Rádio da ANP', 'RSS', 'Leia mais', 'Busca Avançada',
                 'Mapa do Site', 'Acessibilidade', 'Contato', 'Página Inicial',
                 'Acessar', 'ASSEMBLEIA NACIONAL POPULAR', 'Mais vídeos…',
                 'Mais vídeos', 'Galeria de Vídeos', 'Galeria de Fotos',
                 'Galeria de Áudios'}
        if link_text in noise or link_text.startswith('contato@'):
            continue

        # Resolve relative URLs
        if href.startswith('/'):
            href = BASE_URL + href
        elif not href.startswith('http'):
            href = category_url.rstrip('/') + '/' + href

        # Skip navigation, RSS, external links, anchors, login, search, pagination
        if any(skip in href for skip in ['/RSS', '/login', '/@@', '/sitemap',
                '/accessibility', '/contact', '#', 'facebook.com', 'interlegis',
                'parlamento.pt', 'instituto-camoes', 'secomunidades', 'guine.org',
                'asg-plp.org', '.mp3', '?month=', '&year=', '&amp;']):
            continue
        # Skip external links
        if not href.startswith(BASE_URL):
            continue

        # Only include links under /leis/ that go deeper than the category
        path = href.replace(BASE_URL, '').rstrip('/')
        if not path.startswith('/leis/'):
            continue

        parts = [p for p in path.split('/') if p]
        if len(parts) <= 2:  # Just /leis/category — not a document
            continue

        # Skip if it's another category listing (not a document)
        if path in [f'/leis/{cat[0]}' for cat in CATEGORIES]:
            continue

        # Must be under the current category
        if not path.startswith(cat_path + '/'):
            continue

        # Skip PDF direct links (we handle them on the document page)
        if '.pdf' in path.lower():
            continue

        links.append((href, link_text))

    # Deduplicate by URL
    seen = set()
    unique = []
    for url, title in links:
        url = url.rstrip('/')
        if url not in seen:
            seen.add(url)
            unique.append((url, title))
    return unique


def find_pdf_links(html: str, page_url: str) -> List[str]:
    """Find PDF download links on a document page."""
    pdfs = []
    for match in re.finditer(r'href="([^"]*\.pdf(?:/[^"]*)?)"', html, re.IGNORECASE):
        href = match.group(1)
        if href.startswith('/'):
            href = BASE_URL + href
        elif not href.startswith('http'):
            href = page_url.rstrip('/') + '/' + href
        # Plone serves PDF downloads via /at_download/file
        if '/at_download/file' in href:
            pdfs.insert(0, href)  # Prioritize direct download links
        elif href.endswith('/view'):
            # Try the at_download path instead
            dl_url = href.replace('/view', '/at_download/file')
            pdfs.append(dl_url)
            pdfs.append(href)
        else:
            # Also try at_download path
            pdfs.append(href + '/at_download/file')
            pdfs.append(href)
    return pdfs


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Try to extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return '\n\n'.join(pages_text)
    except Exception as e:
        print(f"    pdfplumber failed: {e}")

    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(io.BytesIO(pdf_bytes))
        return text.strip()
    except Exception as e:
        print(f"    pdfminer failed: {e}")

    return ""


def extract_date_from_text(text: str, title: str) -> Optional[str]:
    """Try to extract a date from the document text or title."""
    combined = title + ' ' + text[:2000]
    # Patterns like "Lei N.º 2/98 de 23 de Abril"
    months_pt = {
        'janeiro': '01', 'fevereiro': '02', 'março': '03', 'marco': '03',
        'abril': '04', 'maio': '05', 'junho': '06',
        'julho': '07', 'agosto': '08', 'setembro': '09',
        'outubro': '10', 'novembro': '11', 'dezembro': '12',
    }
    # Pattern: "de DD de Month de YYYY"
    match = re.search(r'de\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', combined, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))
        month = months_pt.get(month_name)
        if month and 1900 <= year <= 2030:
            return f"{year}-{month}-{day:02d}"

    # Pattern: "DD de Month de YYYY"
    match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', combined, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))
        month = months_pt.get(month_name)
        if month and 1900 <= year <= 2030:
            return f"{year}-{month}-{day:02d}"

    # Pattern: "DD/MM/YYYY"
    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', combined)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"

    # Pattern: "DD-MM-YYYY"
    match = re.search(r'(\d{2})-(\d{2})-(\d{4})', combined)
    if match:
        year = int(match.group(3))
        if 1900 <= year <= 2030:
            return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"

    return None


def make_doc_id(url: str) -> str:
    """Create a document ID from URL."""
    path = url.replace(BASE_URL, '').strip('/')
    # Simplify: take the last meaningful slug
    parts = [p for p in path.split('/') if p and p != 'leis' and p != 'view']
    slug = '_'.join(parts[-2:]) if len(parts) >= 2 else '_'.join(parts)
    slug = re.sub(r'[^\w-]', '_', slug)
    return f"GW_AN_{slug}"


def normalize(title: str, text: str, url: str, category: str) -> Dict:
    """Normalize a document to standard schema."""
    date = extract_date_from_text(text, title)
    doc_id = make_doc_id(url)

    return {
        '_id': doc_id,
        '_source': SOURCE_ID,
        '_type': 'legislation',
        '_fetched_at': datetime.now(timezone.utc).isoformat(),
        'title': title,
        'text': text,
        'date': date,
        'url': url,
        'category': category,
        'language': 'pt',
    }


def fetch_document(url: str, title: str, category: str) -> Optional[Dict]:
    """Fetch a single document page and extract full text."""
    print(f"  Fetching: {title[:60]}...")
    html = curl_get(url)
    if not html:
        print(f"    Failed to fetch {url}")
        return None

    # Try HTML content extraction first
    text = extract_content_from_html(html)

    # If HTML text is too short, try PDF links on the page
    if len(text) < 200:
        pdf_links = find_pdf_links(html, url)
        for pdf_url in pdf_links:
            print(f"    Trying PDF: {pdf_url.split('/')[-1]}")
            pdf_bytes = curl_get_binary(pdf_url)
            if pdf_bytes and len(pdf_bytes) > 500:
                # Check if it's actually a PDF (not HTML error page)
                if pdf_bytes[:5] == b'%PDF-':
                    pdf_text = extract_text_from_pdf(pdf_bytes)
                    if len(pdf_text) > len(text):
                        text = pdf_text
                        print(f"    PDF extracted: {len(text)} chars")
                        break
                else:
                    print(f"    Not a valid PDF (starts with {pdf_bytes[:20]})")

    if not text or len(text) < 200:
        print(f"    Insufficient text ({len(text)} chars), skipping")
        return None

    record = normalize(title, text, url, category)
    print(f"    OK: {len(text)} chars")
    return record


def fetch_known_document(path: str, title: str, category: str, source_type: str) -> Optional[Dict]:
    """Fetch a known document by path and type."""
    url = BASE_URL + path
    print(f"  Fetching: {title[:60]}...")

    if source_type == "pdf":
        pdf_bytes = curl_get_binary(url)
        if not pdf_bytes or len(pdf_bytes) < 500:
            print(f"    Failed to download PDF")
            return None
        if pdf_bytes[:5] != b'%PDF-':
            print(f"    Not a valid PDF file")
            return None
        text = extract_text_from_pdf(pdf_bytes)
        if not text or len(text) < 50:
            print(f"    PDF text extraction failed ({len(text) if text else 0} chars)")
            return None
        print(f"    PDF OK: {len(text)} chars")
    else:
        html = curl_get(url)
        if not html:
            print(f"    Failed to fetch")
            return None
        text = extract_content_from_html(html)
        if not text or len(text) < 50:
            print(f"    Insufficient text ({len(text) if text else 0} chars)")
            return None
        print(f"    OK: {len(text)} chars")

    return normalize(title, text, url, category)


def fetch_all() -> Iterator[Dict]:
    """Yield all documents with full text."""
    seen_urls = set()

    # First: fetch known documents (guaranteed to work)
    print("=== Fetching known documents ===")
    for path, title, category, source_type in KNOWN_DOCUMENTS:
        url = BASE_URL + path
        record = fetch_known_document(path, title, category, source_type)
        if record:
            seen_urls.add(url)
            # For PDFs, also mark the parent HTML page as seen to avoid duplicates
            if source_type == "pdf":
                parent = url.rsplit('/', 1)[0]
                seen_urls.add(parent)
            yield record
        time.sleep(REQUEST_DELAY)

    # Then: crawl categories for any additional documents
    print("\n=== Crawling categories for additional documents ===")
    for cat_slug, cat_name in CATEGORIES:
        cat_url = f"{LAWS_URL}/{cat_slug}"
        html = curl_get(cat_url)
        if not html:
            continue

        links = extract_links_from_category(html, cat_url)
        for url, title in links:
            if url in seen_urls:
                continue
            record = fetch_document(url, title, cat_name)
            if record:
                seen_urls.add(url)
                yield record
            time.sleep(REQUEST_DELAY)


def fetch_updates(since: str) -> Iterator[Dict]:
    """Yield documents — for a static site, same as fetch_all."""
    yield from fetch_all()


def bootstrap_sample(max_records: int = 15) -> List[Dict]:
    """Fetch sample records from all categories."""
    samples = []
    for record in fetch_all():
        samples.append(record)
        if len(samples) >= max_records:
            break
    return samples


def main():
    parser = argparse.ArgumentParser(description='GW/AssembleiaNacional Data Fetcher')
    parser.add_argument('command', choices=['bootstrap', 'fetch', 'updates'])
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--since', type=str)
    parser.add_argument('--output', type=str)
    parser.add_argument('--full', action='store_true', help='Fetch all records')
    args = parser.parse_args()

    output_dir = args.output or str(Path(__file__).parent / 'sample')
    os.makedirs(output_dir, exist_ok=True)

    if args.command == 'bootstrap':
        records = bootstrap_sample() if args.sample else list(fetch_all())

        saved = 0
        for record in records:
            filename = re.sub(r'[^\w-]', '_', record['_id'])[:100] + '.json'
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            saved += 1

        print(f"\n=== Summary ===")
        print(f"Records saved: {saved}")
        if records:
            texts = [r['text'] for r in records if r.get('text')]
            avg_len = sum(len(t) for t in texts) / len(texts) if texts else 0
            print(f"Average text length: {avg_len:.0f} chars")
            print(f"All have text: {all(r.get('text') for r in records)}")

    elif args.command == 'fetch':
        count = 0
        for record in fetch_all():
            filename = re.sub(r'[^\w-]', '_', record['_id'])[:100] + '.json'
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
        print(f"Fetched {count} records")

    elif args.command == 'updates':
        if not args.since:
            print("ERROR: --since required")
            sys.exit(1)
        count = 0
        for record in fetch_updates(args.since):
            filename = re.sub(r'[^\w-]', '_', record['_id'])[:100] + '.json'
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            count += 1
        print(f"Fetched {count} updates since {args.since}")


if __name__ == '__main__':
    main()
