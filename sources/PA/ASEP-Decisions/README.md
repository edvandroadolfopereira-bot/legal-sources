# PA/ASEP-Decisions — Panama ASEP (Autoridad Nacional de los Servicios Públicos)

Regulatory resolutions issued by Panama's national public-services regulator,
covering **telecommunications, electricity, water & sewage, and radio & TV**, plus
the **Comisión Sustanciadora** (administrative sanctioning decisions).

## Data access

- **Method:** Official WordPress REST API — `https://asep.gob.pa/wp-json/wp/v2/posts`
- **Auth:** none
- Each resolution is a WordPress post. The post body carries the official
  *sumilla* (one-line summary, "Por la cual …") and embeds the signed
  resolution PDF through a `pdf-viewer` iframe (`viewer.html?file=…pdf`).
- The scraper extracts the embedded PDF URL, downloads the PDF, and extracts its
  **full text** with `pdfplumber`.

## Categories covered

| WP id | Category | Approx. posts |
|-------|----------|---------------|
| 261 | Comisión Sustanciadora | ~1,000 |
| 278 | Resoluciones Electricidad | ~11,500 |
| 108 | Resoluciones Telecomunicaciones | ~11,000 |
| 111 | Resoluciones Radio y Televisión | ~5,700 |
| 110 | Resoluciones Agua y Alcantarillado | ~400 |
| 335 | Resoluciones Atención al Usuario | a few |

## Full-text note

Comisión Sustanciadora resolutions are reliably born-digital with a real text
layer (good full-text yield). Some **recent** sector resolution PDFs are signed
scans with **no text layer**; the scraper detects these (< 400 extracted chars)
and skips them rather than emitting metadata-only records.

## Usage

```bash
python bootstrap.py test-api            # connectivity + per-category counts
python bootstrap.py bootstrap --sample  # 15 sample records with full text
python bootstrap.py bootstrap           # full crawl
```

## License

[Open Government Data](https://asep.gob.pa/) — official acts of a Panamanian
government authority, published for public access. No explicit reuse license is
stated; treated as open government data. Attribution to ASEP recommended.
