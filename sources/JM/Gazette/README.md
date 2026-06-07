# JM/Gazette

Jamaica Official Gazette — proclamations, rules, regulations, and appointed day
notices published by the Ministry of Justice.

## Data

- ~9,200+ gazette entries (2000-2024)
- Full text extracted from freely accessible PDFs
- Covers proclamations, subsidiary legislation, emergency regulations

## Strategy

1. DataTables server-side POST API at `/library/gazettes/{year}` for listings
2. Parse detail pages for PDF viewer paths (`data-pdfjs-target="pdf"`)
3. Download PDFs and extract text via pdfplumber/pypdf
4. One record per gazette notice

## License

[Jamaica Ministry of Justice](https://laws.moj.gov.jm/) — official government gazette, freely accessible online. Attribution to the Ministry of Justice required.
