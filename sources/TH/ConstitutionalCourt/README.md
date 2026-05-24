# TH/ConstitutionalCourt — Thailand Constitutional Court Decisions

Constitutional review decisions from the Constitutional Court of Thailand,
sourced via the court's Intelligent Search System (ISS) API at
`iss.constitutionalcourt.or.th`.

The ISS indexes ~12,000 Thai Constitutional Court records (rulings and orders).
About 1,200+ of these are ruling summaries with digitally-embedded Thai text
that can be extracted from PDFs. The remainder are scanned-image PDFs without
embedded text (OCR would be required).

This scraper fetches records via the ISS REST API, downloads PDF attachments,
and extracts text using pdfplumber. Records without extractable text are skipped.

## Data types

- `case_law` — constitutional review rulings and court orders

## License

[Thai Government Publication](https://www.constitutionalcourt.or.th/) — decisions
published by the Constitutional Court for public access. No explicit license
specified; Thai government publications are generally considered public domain.
