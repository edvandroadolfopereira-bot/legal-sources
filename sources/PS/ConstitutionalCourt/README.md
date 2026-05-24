# PS/ConstitutionalCourt — Palestinian Supreme Constitutional Court

Fetches decisions from the Palestinian Supreme Constitutional Court
(المحكمة الدستورية العليا), established 2016.

## Data

Three categories of court documents:
- **Court provisions** (احكام المحكمة) — ~128 constitutional review decisions
- **Court decisions** (قرارات المحكمة) — ~41 interpretive decisions
- **Competence disputes** (دعاوى التنازع) — ~7 jurisdiction conflict rulings

All documents are in Arabic, published as PDFs with extractable text.
Total: ~176 documents (2016–present).

## Method

HTML scraping of accordion pages + PDF download and text extraction via `pypdf`.
SSL verification disabled (site has certificate issues but is the official .ps domain).

## License

[Public domain](https://www.tscc.pna.ps) — official government court decisions under Palestinian law.
