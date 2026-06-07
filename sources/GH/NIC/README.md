# GH/NIC — Ghana National Insurance Commission

Ghana's National Insurance Commission (NIC) regulates the insurance industry
under the Insurance Act, 2021 (Act 1061). This source fetches regulatory
directives, guidelines, and news via the WordPress REST API.

## Data types

- **doctrine**: Regulatory directives, guidelines, and news/press releases

## Strategy

WordPress REST API at `wp-json/wp/v2`:
- **Guidelines/Directives** (pages, parent=27): ~22 regulatory documents with
  full text extracted from linked PDFs via pdfplumber
- **Insurance Act** (pages, parent=9): 1 act with PDF text extraction
- **News** (custom post type "news"): ~108 press releases with inline HTML text
- Total: ~130 documents

## License

[Public Government Documents (Ghana)](https://nicgh.org/) — official
regulatory publications. Attribution required.
