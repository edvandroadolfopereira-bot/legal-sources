# NG/PENCOM — Nigeria National Pension Commission

The National Pension Commission (PenCom) is the regulator of the Nigerian
pension industry, established under the Pension Reform Act 2014. PenCom issues
the regulatory instruments that govern Pension Fund Administrators (PFAs),
Pension Fund Custodians (PFCs), and the Contributory Pension Scheme.

This source collects five categories of official PenCom documents:

1. **Regulations** (legislation) — binding subsidiary legislation such as the
   Regulation on Investment of Pension Fund Assets, the Regulation for the
   Transfer of RSAs, and the Regulation on Administration of Retirement and
   Terminal Benefits.

2. **Guidelines** (doctrine) — operational guidance such as the ICT Guidelines,
   the Guidelines for Personal Pension Plan, and guidelines on micro pensions.

3. **Circulars** (doctrine) — regulatory circulars to operators on day-to-day
   compliance matters.

4. **Frameworks** (doctrine) — supervisory and operational frameworks (e.g.
   risk-based supervision, the Retirement Savings Account Transfer System).

5. **Codes** (doctrine) — codes such as the Code of Corporate Governance for
   Licensed Pension Operators.

All documents are PDF files hosted on the PenCom WordPress site.

## Data access

- Five paginated WordPress category pages under
  `https://www.pencom.gov.ng/category/regulations-guidelines-circulars-frameworks/{category}/`.
- Each document is a PDF under `wp-content/uploads/YYYY/MM/`. The scraper walks
  every page of each category (stopping at the first 404 / empty page), reads
  the document title from the anchor text, and extracts the PDF text with
  `pdfplumber`.
- All PDFs are publicly accessible without authentication. A small number of
  older scanned PDFs with no text layer are skipped.

## License

[Custom Terms (Government)](https://www.pencom.gov.ng/) — official Nigerian
government regulatory documents published by the National Pension Commission
under the Pension Reform Act 2014 for public compliance. Regulations have force
of law as subsidiary legislation. Commercial use of the published material is
permitted.
