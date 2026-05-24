# DO/BCRD-Regulations

Banco Central de la República Dominicana — Regulaciones

Monetary Board resolutions (Resoluciones JM), current financial regulations
(Reglamentos Vigentes), and instructivos from the Central Bank of the Dominican
Republic.

## Data sources

1. **Resoluciones JM** (~244 items) — Monetary Board resolutions via POST API
2. **Reglamentos Vigentes** (~59 PDFs) — Current financial regulations
3. **Instructivos** (~18 PDFs) — Implementation guidelines

All documents are PDFs hosted on `cdn.bancentral.gov.do`. Text is extracted
using pdfplumber.

## API

- `POST /Home/GetJmResolutions` — returns JSON with resolution metadata + PDF URLs
- `POST /Home/GetContentForRender` — returns article HTML containing PDF links
  - Article 2571: Reglamentos Vigentes
  - Article 2573: Instructivos

## License

[Open Government Data](https://datos.gob.do/) — official government regulatory
documents published for public access on the Dominican Republic open data portal.
