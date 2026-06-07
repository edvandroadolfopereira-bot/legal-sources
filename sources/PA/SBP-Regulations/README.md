# PA/SBP-Regulations — Superintendencia de Bancos de Panamá (banking regulations)

Binding prudential regulations (**Acuerdos**) issued by the Junta Directiva of
Panama's banking superintendency. These rulebooks govern banks and fiduciary
companies and implement Panama's AML/CFT (prevención del uso indebido de los
servicios bancarios y fiduciarios) regime.

## Data access

- **Method:** HTML scrape of the official Drupal listing pages, then PDF
  download + text extraction.
- **Auth:** none.
- The acuerdos are listed in Drupal *views-accordion* tables (grouped by year):
  - `/acuerdos/bancarios` — banking acuerdos
  - `/acuerdos/fiduciarios` — fiduciary acuerdos
  - `/acuerdos/prevencion` — AML/CFT-prevention acuerdos
- Each accordion row carries the acuerdo number (`col-sm-2`), the official
  description — purpose + Gaceta Oficial publication reference (`col-sm-9`) —
  and the signed acuerdo PDF (`col-sm-1`). The scraper downloads that PDF and
  extracts its **full text** with `pdfplumber`.

## Full-text note

The great majority of acuerdos are born-digital PDFs with a real text layer
(sample average ≈ 20,000 characters per document). The rare recent acuerdo
published as a signed scan with no text layer is detected (< 400 extracted
characters) and skipped rather than emitted as a metadata-only record.

The acuerdo's enactment date is parsed from the document header; a sanity guard
falls back to the Gaceta Oficial publication date when the header parse would
yield a year inconsistent with the acuerdo's own year (avoids locking onto a
date cited in the body).

## Usage

```bash
python bootstrap.py test-api            # connectivity + per-listing counts
python bootstrap.py bootstrap --sample  # 15 sample records with full text
python bootstrap.py bootstrap           # full crawl
```

## License

[Open Government Data](https://www.superbancos.gob.pa/) — official regulatory
acts of a Panamanian government authority, published for public access. No
explicit reuse license is stated; treated as open government data. Attribution
to the Superintendencia de Bancos de Panamá recommended. Commercial use
permitted.
