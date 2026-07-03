# SC/Judiciary — Judiciary of Seychelles Court Decisions

Full-text court judgments published by the **Judiciary of Seychelles** on its
official "Decisions from the Courts" page (`judiciary.sc`).

## Coverage

- **Court of Appeal**
- **Constitutional Court**
- **Supreme Court (criminal)**
- **Supreme Court (civil)**

Each decision is a downloadable PDF accompanied by structured metadata: case
name, case number, media-neutral citation (e.g. `[2026] SCCC 1`), decision date,
presiding judges, decision type (Judgment / Ruling / Order), and a keyword
summary.

This is the **official judiciary source** and is distinct from SeyLII
(`seylii.org`), which is currently blocked (infrastructure / Lexum platform
endpoints non-functional).

## Access

- Discovery: per-court HTML tables on
  `https://www.judiciary.sc/resources/court-decisions/`
- Full text: PDF download from `judiciary.sc/wp-content/uploads/{year}/{month}/*.pdf`,
  extracted via `common/pdf_extract` (pdfplumber/pypdf).

## Usage

```bash
python bootstrap.py test                 # health check (count judgments found)
python bootstrap.py bootstrap --sample   # fetch ~12 sample records
python bootstrap.py bootstrap            # full pull
python bootstrap.py bootstrap-fast       # concurrent full pull (VPS)
```

## License

[Public access — Court decisions of the Judiciary of Seychelles](https://www.judiciary.sc/resources/court-decisions/) — court decisions are public judicial acts published free of charge by the Judiciary of Seychelles. Crown Copyright (Seychelles) applies to the underlying documents.
