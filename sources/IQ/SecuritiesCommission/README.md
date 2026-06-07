# IQ/SecuritiesCommission — Iraqi Securities Commission

Regulations, instructions, board decisions, and related laws from the
[Iraqi Securities Commission](https://www.isc.gov.iq/en) (ISC).

## Data types

| Category | Format | Count |
|----------|--------|-------|
| Commission Law | PDF | 1 |
| Related Laws | PDF | 3 |
| Instructions & Regulations | PDF | ~48 |
| Board Decisions | HTML+PDF | ~27 |

## Strategy

1. Scrape listing pages for each legislation category (Arabic pages for regulations, English for laws)
2. For PDFs: download and extract text with pdfplumber
3. For board decisions: fetch detail pages, try PDF extraction first, fall back to HTML text

## License

[Open Government Data](https://www.isc.gov.iq/en) — official Iraqi government regulatory documents published for public access.
