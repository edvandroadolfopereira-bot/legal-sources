# HN/BCH-Regulations — Banco Central de Honduras, Marco Legal

Full text of the legal and regulatory framework published by the **Banco
Central de Honduras (BCH)**, the central bank of Honduras, on its
*Marco Legal / Leyes y Reglamentos* page.

## What this covers

- **Laws & decrees** — Ley del Banco Central de Honduras (Decreto No. 53),
  Ley del Sistema Financiero (Decreto No. 129-2004), Ley de Equidad
  Tributaria, the Constitución de la República, and related decretos.
- **BCH normative instruments** — *circulares*, *resoluciones* and
  *acuerdos* issued by the BCH Directorio implementing monetary policy,
  exchange / FX-market policy, payment systems, the securities depositary
  (DV-BCH), reserve requirements, AML/CFT and credit policy.

Classified as **legislation** (statutes plus central-bank regulations).

## How it works

The page is backed by a public SharePoint document library
(`/administrativas/JUR/Marco Legal OM 2/`) whose contents are exposed
**without authentication** via the SharePoint REST API:

```
/administrativas/JUR/_api/web/GetFolderByServerRelativeUrl('<folder>')/Files
  ?$select=Name,ServerRelativeUrl,TimeLastModified&$top=2000
```

We list every PDF (~760 documents), download each directly from its
`ServerRelativeUrl`, and extract the full text with `pdfplumber`. Titles
and dates are parsed from the document header, with the file name as a
fallback. PDFs that yield fewer than 500 characters are skipped.

## Usage

```bash
python bootstrap.py test               # connectivity test
python bootstrap.py bootstrap --sample # sample mode (default 15)
python bootstrap.py bootstrap          # full pull
python bootstrap.py update             # re-fetch (upsert by URL)
```

## Record schema

`_id`, `_source` (`HN/BCH-Regulations`), `_type` (`legislation`),
`_fetched_at`, `title`, `text` (full text), `date`, `url`, `doc_number`,
`doc_kind`, `issuer`, `jurisdiction` (`HN`), `language` (`es`),
`source_file`, `modified`, `pdf_size`.

## License

[Open Government Data (Honduras)](https://www.bch.hn/) — Honduran official
legal texts (laws, decrees) and central-bank regulatory instruments
published by the Banco Central de Honduras on its institutional website for
public use. Official legal texts are not subject to copyright. Commercial
use permitted; attribution to the BCH appreciated.
