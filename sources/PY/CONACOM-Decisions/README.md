# PY/CONACOM-Decisions — Paraguay Competition Authority Decisions

Decisions and case files of the **Comisión Nacional de la Competencia (CONACOM)**,
Paraguay's national competition authority, which enforces *Ley N° 4956/2013 de
Defensa de la Competencia*.

## Data source

- Site: https://conacom.gov.py/
- Listing pages (one row per released document, with a Google Drive PDF link):
  - Restrictive practices: https://conacom.gov.py/practicas/historial/
  - Merger / concentration control: https://conacom.gov.py/concentraciones/expedientes/

Each case (expediente) is an accordion card containing a table of documents:
`Fecha | ID (e.g. RAL 2017/001) | Descripción | Enlace`. Document types include
resoluciones administrativas del Directorio (RAL), pareceres de la Dirección de
Investigación (DIPARCC), autorizaciones de concentración, medidas cautelares, and
sanctions.

## Method

1. Fetch the two listing pages and parse the accordion tables.
2. For each row, download the linked Google Drive PDF
   (`https://drive.google.com/uc?export=download&id=<id>`).
3. Extract full text via `common.pdf_extract` (opendataloader → pdfplumber → pypdf).
4. CONACOM publishes a **mix of digital (text-layer) and scanned image PDFs**.
   Scanned PDFs yield no extractable text and are **skipped** — only documents whose
   full text can be extracted are emitted.

```bash
python bootstrap.py test-api            # connectivity + one extraction
python bootstrap.py bootstrap --sample  # sample records for validation
python bootstrap.py bootstrap           # full run
```

## Output schema

`_id`, `_source` (`PY/CONACOM-Decisions`), `_type` (`case_law`), `_fetched_at`,
`title`, `text` (full document text), `date`, `url`, `case`, `resolution_id`,
`description`, `category` (`practicas` | `concentraciones`).

## License

[Open Government Data (Paraguay)](https://www.conacom.gov.py/) — official decisions
of a Paraguayan public authority, published online for public access. No explicit
reuse license is attached; treated as open government data (commercial use permitted,
no attribution requirement stated).
