# BH/PDP — Bahrain Personal Data Protection Authority

Scrapes the Personal Data Protection Authority website
(`https://www.pdp.gov.bh/en/`) for:

- **The Law** — Personal Data Protection Law (Law No. 30 of 2018)
- **Royal Decree** — the underlying decree
- **Executive Decisions / Orders** — ~20 implementing orders covering
  auditor fees, complaints, sensitive-data processing, cross-border
  data transfers, notifications, etc. (Arabic + English)

The site is a static set of HTML pages with PDFs on the same
CloudFront-fronted bucket. There is no API. CloudFront returns 403 for
the default `requests` user-agent, so the scraper downloads PDFs
itself and passes the bytes to `common.pdf_extract.extract_pdf_markdown`.

## Usage

```
python bootstrap.py test                  # connectivity + listing
python bootstrap.py bootstrap --sample    # 15 sample records
python bootstrap.py bootstrap             # full pull (~22 PDFs)
```

## License

Public Domain (Government of Bahrain) — official government publication, no
copyright asserted. Republished with link back to `pdp.gov.bh`.
