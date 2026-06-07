# CR/SUTEL-Regulations — Superintendencia de Telecomunicaciones

Full-text regulatory output of Costa Rica's telecommunications regulator
**SUTEL** (Superintendencia de Telecomunicaciones).

- **Country:** CR (Costa Rica)
- **Type:** `doctrine` (regulatory resolutions / normativa)
- **Language:** Spanish
- **Auth:** none
- **URL:** https://www.sutel.go.cr/

## What it collects

Two areas of the SUTEL Drupal site are enumerated:

| Source | Documents |
|--------|-----------|
| `/sutel/resoluciones` | "Principales Resoluciones y Acuerdos del Consejo" — RCS-numbered Council resolutions issued since 2009, covering interconnection, spectrum, shared-use offers, universal-access/FONATEL funding, parafiscal contributions, minimum-speed parameters, and sanctions (e.g. `RCS-298-2025`, `RCS-005-2026`). |
| `/normativas` | SUTEL's own reglamentos, lineamientos, and policy documents (e.g. the Política de Infraestructura, PNDT). |

Each record carries the full extracted text, a descriptive title, the
resolution identifier (`doc_number`, e.g. `RCS-298-2025`, null for
reglamentos), the `category` (resolucion / reglamento / lineamientos /
acuerdo / politica / normativa), the issuer, and a best-effort issue date.

Laws authored by other bodies (e.g. the Ley General de Telecomunicaciones)
are excluded by filename — they belong to legislation sources.

## How it works

1. The paginated resoluciones view and the `/normativas` page are scraped
   for `href="*.pdf"` links, which are de-duplicated and filtered (external
   laws, forms, FAQs, and slide decks are dropped).
2. Each PDF is downloaded and its text extracted with `pdfplumber`.
3. Text is cleaned (whitespace normalised) and a Spanish-format date is
   parsed best-effort from the document text.

TLS verification is disabled because `sutel.go.cr` serves an incomplete
certificate chain; the data is public and read-only.

## Usage

```bash
python bootstrap.py test                # connectivity smoke test
python bootstrap.py bootstrap --sample  # 15 sample records
python bootstrap.py bootstrap --full    # full corpus
python bootstrap.py update              # re-discover; upsert dedups
```

## License

[Open Government Data (Costa Rica)](https://www.sutel.go.cr/) — official
regulatory resolutions and reglamentos published by a Costa Rican public
institution (SUTEL) for public use. Commercial use permitted; attribution
to the issuing authority is expected.
