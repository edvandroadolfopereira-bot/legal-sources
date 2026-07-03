# US/CA-AGOpinions — California Attorney General Formal Opinions

Full text of formal legal opinions issued by the California Office of the
Attorney General. Each opinion answers a legal question posed by a public
official (legislator, district attorney, agency head, etc.) and constitutes
an authoritative — though advisory — interpretation of California law.

## Data source

- **Publisher:** California Office of the Attorney General (oag.ca.gov)
- **Index:** https://oag.ca.gov/opinions/yearly-index
- **Access method:** HTML index (one table per year, filtered via the
  `conclusion-year[value][year]=YYYY` query parameter) linking to official
  opinion PDFs. Full text is extracted from each PDF with `pdfplumber`.
- **Coverage:** 1976–present, roughly 6–15 opinions per year (~500+ documents).
- **Auth:** none. Public government data.
- **Type:** doctrine (official state legal interpretation).

## Fields

Each record contains `_id`, `_source`, `_type`, `_fetched_at`,
`opinion_number`, `title`, `text` (full opinion body), `question`,
`conclusion`, `url`, and `date` (ISO 8601, date issued).

## Usage

```bash
python bootstrap.py test-api             # connectivity + extraction test
python bootstrap.py bootstrap --sample   # ~12 sample documents
python bootstrap.py bootstrap            # full pull (all years)
python bootstrap.py bootstrap-fast       # alias for full pull
```

## License

[Public Domain — US Government Work (California)](https://www.law.cornell.edu/uscode/text/17/105) — California Attorney General opinions are official state government works in the public domain. No attribution required; commercial use permitted.
