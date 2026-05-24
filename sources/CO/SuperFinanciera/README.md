# CO/SuperFinanciera

**Superintendencia Financiera de Colombia** — Circulares Externas, Cartas Circulares, and Resoluciones from Colombia's financial regulatory authority, issued since 2005.

## Coverage

- **Circulares Externas**: General regulatory instructions for supervised financial entities
- **Cartas Circulares**: Administrative circular letters
- **Resoluciones**: Formal regulatory resolutions

Documents cover banking, insurance, pensions, securities markets, and consumer financial protection.

## Data Access

Documents are published as PDFs on the SuperFinanciera website, organized by year and type. The scraper:
1. Parses the year index pages to get document metadata
2. Downloads individual PDF files via `loader.php` endpoints
3. Extracts full text using pdfminer

## License

[Open Government Data (Colombia)](https://www.superfinanciera.gov.co/) — official regulatory documents published by a Colombian government agency. Attribution required.
