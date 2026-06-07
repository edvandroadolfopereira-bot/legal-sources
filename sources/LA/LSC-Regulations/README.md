# LA/LSC-Regulations — Lao Securities Commission Office (Capital Market Regulations)

Official English-language capital-market legal corpus published by the **Lao
Securities Commission Office (LSC)**, the regulator of Laos's securities and
capital markets.

- **Country:** Laos (LA)
- **Publisher:** Lao Securities Commission Office — https://lsc.gov.la/EN/
- **Data type:** legislation (laws, regulations, decisions, guidelines/instructions, notifications)
- **Auth:** none
- **Full text:** yes — extracted from PDFs via `pdfplumber`

## What it collects

The LSC site lists its legal documents in PHP tables under
`https://lsc.gov.la/EN/legislation/` across several categories (laws, regulation,
guideline, notification, agreement/decision, etc.). Each row links to a PDF under
`https://lsc.gov.la/Doc_legal/`. The scraper walks every category's listing pages,
keeps only rows that point at a real `Doc_legal/*.pdf`, downloads each PDF, and
extracts the full text.

Captured fields: `title`, `text` (full document body), `date` (ISO 8601),
`reference_number`, `category`, and the source `url`.

Coverage is the English corpus the LSC publishes — the foundational **Law on
Securities (Amended)** plus ~15 regulations, decisions, instructions and
notifications. The `proposed_to_lsc` category is intentionally excluded: it
contains third-party vendor submissions (e.g. price quotations), not legislation.

## Usage

```bash
python bootstrap.py bootstrap            # full pull
python bootstrap.py bootstrap --sample   # sample records (writes sample/*.json)
python bootstrap.py test                 # connectivity test
```

## Notes

- A small number of links on the site are broken (HTTP 404) or occasionally drop
  the connection; the scraper skips these and continues.
- There is no incremental/changes API, so `update` re-fetches the full corpus.

## License

[Public Domain — Government of Laos official legal texts](https://lsc.gov.la/EN/) —
official regulatory documents published by the Lao Securities Commission Office for
public compliance. Laos has no formal open-data licence; government statutes and
regulatory instruments carry no copyright restriction on reproduction. Commercial
use permitted.
