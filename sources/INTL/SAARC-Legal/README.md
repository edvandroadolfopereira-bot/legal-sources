# INTL/SAARC-Legal

SAARC Legal Instruments — Conventions, Agreements & Summit Declarations from the
South Asian Association for Regional Cooperation (8 member states: AF, BD, BT, IN, MV, NP, PK, LK).

## Data Source

- **Website:** https://www.saarc-sec.org/
- **API:** CMS JSON API at `/api/pages/{slug}`
- **Format:** PDF documents + inline HTML (Charter)
- **Coverage:** 28 agreements/conventions + 17 summit declarations + Charter = ~46 instruments

## Method

1. Fetches page content from `/api/pages/agreements-conventions` and `/api/pages/summit-declarations`
2. Parses HTML to extract PDF links with titles
3. Downloads PDFs and extracts text via pdfplumber
4. Charter text is extracted directly from inline HTML at `/api/pages/saarc-charter`

## License

[SAARC Official Publications](https://www.saarc-sec.org/) — official legal instruments of an international organization, published for open public access. Attribution required.
