# MZ/TSLegislacao — Mozambique Supreme Court Legislation Portal

Legislation published by the Tribunal Supremo de Moçambique (Supreme Court of Mozambique).

- **URL**: https://www.ts.gov.mz/legislacao/
- **Data type**: Legislation
- **Records**: ~112 PDFs (constitutions, laws, decrees, resolutions, directives)
- **Coverage**: 1975–2026
- **Language**: Portuguese

## How it works

The legislation page is a WordPress page (ID 95) containing links to PDF documents.
The scraper fetches the page content via the WP REST API, extracts all PDF URLs and
their link text (titles), downloads each PDF, and extracts full text using pdfplumber.

## License

[Public Domain (Government)](https://www.ts.gov.mz/legislacao/) — Official legislation of the Republic of Mozambique is public domain.
