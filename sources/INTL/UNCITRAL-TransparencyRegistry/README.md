# INTL/UNCITRAL-TransparencyRegistry

UNCITRAL Transparency Registry — central repository of investor-state arbitration
documents under the UNCITRAL Rules on Transparency in Treaty-based Investor-State
Arbitration (effective 1 April 2014).

## Data

- ~33 registered cases
- Documents include: notices of arbitration, awards, decisions, pleadings, procedural orders
- Full text extracted from freely accessible PDFs
- Covers disputes under NAFTA Chapter 11, various BITs, and FTAs

## Strategy

1. Scrape search pages at `search.jspx` (paginated, 10 per page)
2. Parse each case detail page for metadata + document table
3. Download PDFs and extract text via pdfplumber/PyPDF2
4. One record per document (not per case)

## License

[United Nations Terms of Use](https://www.un.org/en/about-us/terms-of-use) — UN documents are generally freely reproducible with attribution to the United Nations.
