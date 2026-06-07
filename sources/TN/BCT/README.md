# TN/BCT — Central Bank of Tunisia: Circulars & Regulations

Fetches circulars and regulatory notes from the Central Bank of Tunisia (BCT)
circulars page. Downloads each PDF and extracts full text with pdfplumber.

- **Country:** Tunisia (TN)
- **Type:** Doctrine (regulatory circulars and notes)
- **Coverage:** 2016–present (~460 documents)
- **Language:** French and Arabic

## Strategy

1. Scrape the BCT circulars listing page for all PDF links
2. Parse reference numbers and dates from link text
3. Download each PDF and extract text with pdfplumber
4. Skip documents with insufficient text (scanned/image PDFs)

## License

[Public Domain (Government)](https://www.bct.gov.tn/bct/siteprod/documents/termes_an.pdf) — official central bank regulatory publications.
