# VC/NTRC — SVG National Telecommunications Regulatory Commission

Telecommunications legislation and regulations for Saint Vincent and the Grenadines,
published by the National Telecommunications Regulatory Commission (NTRC).

**URL:** https://www.ntrc.vc/providers/legislation/

## Coverage

- Telecommunications Act (Cap 418)
- ECTEL Treaty 2000
- ~15 subsidiary regulations (spectrum, interconnection, licensing, tariffs, dispute resolution, USF, numbering, etc.)
- Related acts (Consumer Protection Act 2020, Electronic Transactions Act 2015, Electronic Filing Act 2015)

## Data Types

- `legislation` — all documents are acts and regulations

## Method

HTML scraping of the legislation page to extract PDF links, then PDF text extraction
via `pdfplumber`. All documents are served as static PDFs from `ntrc.vc/docs/legislations/`.

## License

[Open Government Data](https://www.ntrc.vc/providers/legislation/) — official government legislation, publicly available. No explicit license terms stated; government regulatory documents published for public access.
