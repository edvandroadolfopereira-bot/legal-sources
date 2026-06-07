# INTL/UEFA-Disciplinary

UEFA Disciplinary Decisions & Regulations — decisions from the Control, Ethics and Disciplinary Body (CEDB) and Appeals Body (AB), plus all public UEFA regulations and statutes.

## Data Sources

1. **Regulations** (legislation): Fetched via the Knowledge Hub JSON API at `documents.uefa.com/api/khub/documents`. ~26 English public documents including statutes, disciplinary regulations, organisational regulations, and guidelines.

2. **Disciplinary Decisions** (case_law): PDF links scraped from the UEFA meeting-decisions page. ~60 decision PDFs from CEDB panel sessions, CEDB judges sitting alone (JSA), and Appeals Body sessions, dating from March 2025 onwards.

Both streams download PDFs and extract full text using pdfminer.

## Technical Notes

- Uses `curl` subprocess for HTTP (Python requests gets 403 from UEFA bot protection, and Python 3.9's LibreSSL is too old for documents.uefa.com TLS)
- The `--http1.1` flag is required for www.uefa.com
- pdfminer warnings about invalid color values are harmless and do not affect text extraction

## License

> ⚠️ **Commercial use restricted.** See terms below.

[UEFA General Terms](https://www.uefa.com/general-terms/) — UEFA publishes decisions and regulations for transparency purposes. Commercial redistribution restricted under UEFA's general terms of use.
