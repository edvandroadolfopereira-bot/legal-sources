# GN/BCRG-Regulations — Central Bank of Guinea Regulatory Texts

Regulatory texts from the Banque Centrale de la République de Guinée (BCRG).

Covers: banking law, insurance code, microfinance regulations, AML/compliance,
monetary policy instructions, and payment systems framework.

- **Source:** https://www.bcrg-guinee.org/
- **Language:** French
- **Format:** PDF files embedded in WordPress pages
- **Volume:** ~50 regulatory pages with embedded PDFs

## Strategy

1. Parse sitemap for all page URLs
2. Filter for regulatory/legal content pages
3. Scrape each page to find embedded PDF URLs (dFlip viewer or wp-content/uploads)
4. Download PDFs and extract text via pypdf/pdfplumber
5. Skip scanned-image PDFs with no extractable text

## License

[Public Domain — Government of Guinea](https://www.bcrg-guinee.org/) — official central bank regulatory publications. No explicit license stated; government regulatory texts are presumed public.
