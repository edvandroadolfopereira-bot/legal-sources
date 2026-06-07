# HN/CNBS-Regulations — Comisión Nacional de Bancos y Seguros

Full text of the regulatory framework published by the **Comisión Nacional de
Bancos y Seguros (CNBS)**, the Honduran financial-sector supervisor, on its
public *Resoluciones y circulares* portal (`circulares.cnbs.gob.hn`).

## What this covers

CNBS circulars carry the binding prudential regulation of Honduras:

- **Prudential normas & reglamentos** — loan-portfolio evaluation and
  classification, reserve/encaje requirements, institutional investments,
  capital adequacy, reinsurance, AML/CFT, market conduct, data-capture
  ("capturador") rules for banks, insurers, AFP pension managers, credit-card
  issuers and securities-market participants.
- **Resoluciones** of the CNBS board (Junta) that enact those norms.
- **Administrative circulars** — appointments, holiday notices, temporary
  relief measures, etc.

~2,300 circulars from 1996 to the present. Classified as **legislation**
(financial-sector regulation — "legislation includes regulations").

## How it works

The portal is a DevExpress ASP.NET MVC app. Its circular listing is served as
an HTML partial, filtered by year:

```
/Home/Circulares?filterType=CircularesYear&valueFilter=<year>&page=<n>&lastPageShow=0
```

Paging is **0-indexed** with 20 cards per page. We enumerate every year from
1996 to the current year. Each card exposes the circular title
(`CIRCULAR CNBS No.012/2024`), an optional resolution reference
(`RESOLUCIÓN GAD No.299/15-05-2024`), the `dd/mm/yyyy` date and a one-line
summary, plus a link to the circular PDF:

```
/Archivo/Viewer/<id>/<filename>.pdf
```

Each PDF is downloaded directly and its full text extracted with `pdfplumber`.
A browser User-Agent is sent and TLS verification is disabled (public,
read-only data). PDFs yielding fewer than 180 characters are skipped.

## Usage

```bash
python bootstrap.py test               # connectivity test
python bootstrap.py bootstrap --sample # sample mode (default 15)
python bootstrap.py bootstrap          # full pull (~2,300 circulars)
python bootstrap.py update             # incremental (current + previous year)
```

## Output schema

`_id`, `_source` (`HN/CNBS-Regulations`), `_type` (`legislation`),
`_fetched_at`, `title`, `text` (full PDF text), `date` (ISO), `url`,
`doc_number`, `doc_kind` (`circular` / `resolucion` / `norma`),
`resolution_ref`, `summary`, `issuer`, `jurisdiction` (`HN`), `language`
(`es`), `year`, `pdf_size`.

## License

[Open Government Data (Honduras)](https://www.cnbs.gob.hn/) — Honduran
financial-sector regulatory instruments (circulares, resoluciones, normas)
issued by a public institution, the Comisión Nacional de Bancos y Seguros, and
published on its institutional portal for public use. Official regulatory texts
are not subject to copyright. Commercial use permitted; attribution to the CNBS
expected.
