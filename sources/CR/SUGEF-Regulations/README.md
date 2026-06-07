# CR/SUGEF-Regulations — Superintendencia General de Entidades Financieras

Full-text prudential and financial-sector regulations for Costa Rica,
published by **SUGEF** (Superintendencia General de Entidades Financieras)
and the cross-cutting **CONASSIF** (Consejo Nacional de Supervisión del
Sistema Financiero).

- **Country:** CR (Costa Rica)
- **Type:** `doctrine` (regulatory framework / normativa)
- **Language:** Spanish
- **Auth:** none
- **URL:** https://www.sugef.fi.cr/

## What it collects

Two listing pages enumerate the current regulatory corpus:

| Page | Documents |
|------|-----------|
| `/normativa/normativa_vigente.aspx` | "Acuerdos SUGEF" — e.g. SUGEF 3-06 (suficiencia patrimonial / capital adequacy), SUGEF 11-18 (registration of obligated parties), SUGEF 13-19 (AML/CFT risk prevention), SUGEF 24-22 (entity rating). |
| `/normativa/NormativaTransversal.aspx` | "Normativa Transversal" — CONASSIF acuerdos that apply across all financial supervisors (e.g. CONASSIF 1-10 information & disclosure, CONASSIF 6-18). |

~39 regulation PDFs total. Each record carries the full extracted text,
the acuerdo identifier (`doc_number`, e.g. `SUGEF 3-06`), a descriptive
title pulled from the document heading, the issuer, and a best-effort
issue/version date.

## How it works

1. `_discover()` scrapes both `.aspx` listing pages for `href="*.pdf"`
   links and de-duplicates them (paths are re-normalised to avoid double
   percent-encoding).
2. Each PDF is downloaded and its text extracted with `pdfplumber`.
3. Text is cleaned (letter-spaced headings collapsed, whitespace
   normalised) and a Spanish-format date is parsed best-effort.

TLS verification is disabled because `sugef.fi.cr` serves an incomplete
certificate chain; the data is public and read-only.

## Usage

```bash
python bootstrap.py test               # connectivity + single-doc smoke test
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap --full   # full corpus (~39 docs)
python bootstrap.py update             # re-discover; upsert dedups
```

## License

[Open Government Data (Costa Rica)](https://www.sugef.fi.cr/) — official
regulatory documents published by Costa Rican public institutions (SUGEF /
CONASSIF) for public use. Commercial use permitted; attribution to the
issuing authority is expected.
