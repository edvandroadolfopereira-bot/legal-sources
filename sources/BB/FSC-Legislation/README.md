# BB/FSC-Legislation — Barbados Financial Services Commission: Legislation & Guidelines

Full-text legal framework of the Financial Services Commission of Barbados
(FSC), published as PDFs on [fsc.gov.bb](https://www.fsc.gov.bb/).

## What this source covers

The FSC regulates the **non-bank financial sector** of Barbados — insurance,
securities, mutual funds, credit unions and occupational pensions. This source
collects:

- **Legislation** — the Financial Services Commission Act, the Insurance Act,
  the Co-operative Societies Act, the Securities Act, the Mutual Funds Act, the
  Occupational Pension Benefits Act, the Money Laundering and Financing of
  Terrorism (Prevention and Control) Act, and their amendments and regulations.
- **Doctrine** — industry guidelines, AML/CFT guidelines, statutory reporting
  guidelines, regulatory notices and circulars.

- **Language:** English
- **Document types:** legislation, doctrine
- **Approx. volume:** ~71 full-text PDFs

## Access method

No public API. The scraper walks the FSC legal-framework pages
(`/legislation`, `/industry-guidelines`, `/legislation-guidelines`,
`/regulatory-notices`, `/aml-cft`), collects `/viewPDF/documents/*.pdf` links,
downloads each PDF, and extracts full text with `pdfplumber`. Documents whose
filename/title match Act/Regulation patterns are classified as `legislation`;
guidelines, circulars and notices are classified as `doctrine`. Documents
yielding fewer than 200 characters of extractable text are skipped.

## Usage

```bash
python bootstrap.py bootstrap          # Full initial pull
python bootstrap.py bootstrap --sample # Fetch sample records for validation
python bootstrap.py test               # Quick connectivity test
python bootstrap.py update             # Incremental (recent documents)
```

## License

[Open Government Data](https://www.fsc.gov.bb/) — official legal texts of the
Financial Services Commission of Barbados, published openly as PDFs without
registration. No explicit machine-readable license is stated; treated as open
government data (public legal texts). Commercial use permitted.
