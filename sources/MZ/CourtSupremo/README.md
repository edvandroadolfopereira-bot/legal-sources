# MZ/CourtSupremo — Mozambique Supreme Court (Tribunal Supremo)

Court decisions (acórdãos) from the Supreme Court of Mozambique.

- **Source**: https://www.ts.gov.mz
- **Data type**: Case law
- **Language**: Portuguese
- **Coverage**: ~1400 decisions (1989–present)
- **Method**: WordPress REST API (media endpoint) + PDF text extraction

## How it works

The Tribunal Supremo website runs on WordPress. Court decisions are uploaded as
PDF attachments. The scraper paginates through the `/wp-json/wp/v2/media` endpoint
filtering for PDF files, downloads each PDF, and extracts full text using pdfplumber.

## License

[Public Domain (Government)](https://www.ts.gov.mz) — Official court decisions
of Mozambique are public domain under Mozambican law.
