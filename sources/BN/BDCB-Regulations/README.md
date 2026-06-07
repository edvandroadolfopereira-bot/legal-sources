# BN/BDCB-Regulations — Brunei Darussalam Central Bank Regulations & Guidelines

Regulatory documents issued by the Brunei Darussalam Central Bank (BDCB),
formerly the Autoriti Monetari Brunei Darussalam (AMBD). Covers banking,
capital markets, insurance/takaful, AML/CFT, FinTech, and payment systems.

- **Coverage:** ~340 documents (guidelines, notices, directives, legislation)
- **Language:** English
- **Format:** HTML listing → PDF downloads (cms.bdcb.gov.bn) → full text extraction
- **Type:** doctrine (regulatory guidelines, notices, directives)

## Source

Public regulatory listing at
[bdcb.gov.bn/regulatory/regulations](https://www.bdcb.gov.bn/regulatory/regulations),
paginated. Each entry links to a PDF hosted on `cms.bdcb.gov.bn`. The scraper
paginates the listing, downloads each PDF, and extracts the full text via the
shared `pdf_extract` helper (pdfplumber/pypdf backends).

## License

[Public Domain — Government of Brunei](https://www.bdcb.gov.bn) — Official
regulatory documents published by the central bank for public access. No
explicit license stated; treated as open government data per standard practice
for official government regulatory publications. Commercial use permitted.
