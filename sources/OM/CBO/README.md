# OM/CBO — Central Bank of Oman: Regulations & Circulars

Circulars issued by the Central Bank of Oman (CBO) to licensed banks,
finance companies, and money exchange companies.  Topics include banking
regulation, AML/CFT guidance, payment systems, capital adequacy,
and financial stability frameworks.

## Data access

The CBO website runs on SharePoint.  Individual circulars are published as
PDFs in two document libraries:

- **English** — `/sites/assets/Documents/English/Circulars/{year}/`
- **Global** (bilingual / Arabic-only) — `/sites/assets/Documents/Global/Circulars/{year}/`

The scraper uses the SharePoint REST API to enumerate folders and files,
then downloads each PDF and extracts text with PyMuPDF.

~50 % of circulars are image-based (scanned) PDFs; these are skipped when
text extraction yields fewer than 50 characters.

## Coverage

- **Period:** 2006–present
- **Volume:** ~220 English circulars + ~120 Global circulars
- **Language:** English (primary), Arabic (some Global circulars)
- **Update cadence:** ad-hoc (several per year)

## License

[Public Domain (Government)](https://cbo.gov.om/Pages/Copyright.aspx) — official
government regulatory publications.
