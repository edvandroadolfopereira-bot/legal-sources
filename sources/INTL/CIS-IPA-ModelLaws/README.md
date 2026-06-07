# INTL/CIS-IPA-ModelLaws — CIS Interparliamentary Assembly Model Laws

Fetches model codes, laws, and recommendations adopted by the Commonwealth of
Independent States Interparliamentary Assembly for legislative harmonization
across CIS member states (Azerbaijan, Armenia, Belarus, Kazakhstan, Kyrgyzstan,
Moldova, Russia, Tajikistan, Uzbekistan).

## Data Source

- **URL**: https://iacis.ru/baza_dokumentov/modelnie_zakonodatelnie_akti_i_rekomendatcii_mpa_sng/modelnie_kodeksi_i_zakoni
- **Format**: DOCX files, paginated HTML listing (10 items per page)
- **Records**: ~500 model legislative acts
- **Language**: Russian

## Strategy

1. Paginate through the model laws listing (offset-based: /0, /10, /20, ...)
2. Parse each page for document titles, dates, and DOCX download links
3. Download DOCX files and extract text using python-docx
4. Normalize into standard LDH schema

## License

CIS Interparliamentary Assembly model laws are publicly accessible government documents.
