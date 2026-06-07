# NA/LRDC-LegislationReform — Namibia Law Reform & Development Commission Reports

Reports, discussion papers, working papers and concept papers of the **Law
Reform and Development Commission (LRDC)** of Namibia — the statutory body
(established by the Law Reform and Development Commission Act, 1991) that
examines branches of Namibian law and recommends reform. Each publication is
numbered in the **"LRDC N"** series (ISSN 1026-8405).

These are *doctrine*: official state-authored analyses and recommendations on
law reform, not the enacted legislation itself.

## Data source

The complete, born-digital PDF set is hosted in an open Apache directory index
by the **Legal Assistance Centre** at `https://www.lac.org.na/laws/LRDC/`.
NamibLII (`namiblii.org`), the LRDC's own Legal Information Institute project,
mirrors the same documents under Akoma Ntoso `/akn/na/doc/...` paths, but those
document pages are served behind a Cloudflare JS challenge, so we collect the
PDFs from the LAC directory instead.

## Method

1. List every `*.pdf` in the `/laws/LRDC/` directory index (~34 reports).
2. Download each PDF and extract full text with `pdfplumber`.
3. Derive a clean title from the descriptive filename; parse the publication
   date and the "LRDC N" series number from the PDF cover text.
4. Drop image-only scans with a Latin-text quality filter.

## Usage

```bash
python bootstrap.py test-api            # list discovered PDFs
python bootstrap.py bootstrap --sample  # write sample records
python bootstrap.py bootstrap           # full pull
python bootstrap.py update              # incremental (re-crawl)
```

## Record schema

`_id`, `_source`, `_type` (`doctrine`), `_fetched_at`, `title`, `text`
(full report body), `date`, `url`, `language` (`en`), `series_number`
(e.g. `LRDC 27`), `publisher`.

## License

[Public Domain (Government of Namibia)](https://www.lac.org.na/laws/LRDC/) —
official publications of the Law Reform and Development Commission, a statutory
body of the Republic of Namibia, issued for public access. Mirror hosting by
the Legal Assistance Centre. Commercial use permitted; no attribution required.
