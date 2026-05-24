# IN/SAT — Securities Appellate Tribunal

**Source:** [https://satweb.sat.gov.in/orders](https://satweb.sat.gov.in/orders)
**Data types:** case_law

The Securities Appellate Tribunal (SAT) is a statutory body established under Section 15K of the SEBI Act, 1992. It hears appeals against orders of:
- **SEBI** — Securities and Exchange Board of India
- **IRDAI** — Insurance Regulatory and Development Authority of India
- **PFRDA** — Pension Fund Regulatory and Development Authority

SAT has a single bench located in Mumbai with all-India jurisdiction. Orders are available as PDFs from approximately 2003 to present.

## Strategy

1. GET `/orders` page to extract a CSRF `security_token`
2. POST to `get-orders-by-date` AJAX endpoint with monthly date ranges per appeal type (SEBI/IRDAI/PFRDA)
3. Parse the returned HTML table for case metadata and `view-order/{hash}/{id}` links
4. Download order PDFs and extract full text with `pdfplumber`

## License

[Government Open Data License — India](https://data.gov.in/government-open-data-license-india) — government tribunal orders are public records.
