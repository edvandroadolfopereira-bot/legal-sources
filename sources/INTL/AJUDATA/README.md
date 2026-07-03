# INTL/AJUDATA — African Jurisprudence Database

African Court on Human and Peoples' Rights decisions database (AJUDATA).

- **URL**: https://www.african-court.org/ajudata/
- **Data type**: case_law
- **Records**: ~470 decisions (judgments, orders, rulings, advisory opinions)
- **Coverage**: 2006–present
- **API**: Paginated JSON at `/ajudata/apidata/decisions`

## Strategy

1. Fetch all decisions via paginated JSON API (150 records/page, 4 pages)
2. Download decision PDFs (full judgments preferred, summaries as fallback)
3. Extract text from PDFs using pdfplumber

## License

[Public Domain — Official Court Decisions](https://www.african-court.org/wpafc/online-database/) — decisions of international courts are public records. The African Court publishes all decisions freely on its website without access restrictions.
