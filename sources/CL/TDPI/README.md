# CL/TDPI — Tribunal de Propiedad Industrial

Patent rulings and trademark jurisprudence bulletins from Chile's
Intellectual Property Court (TDPI).

## Data

- **Source**: https://www.tdpi.cl/
- **Type**: case_law
- **Format**: PDF documents scraped from WordPress pages
- **Language**: Spanish
- **Volume**: ~102 patent rulings + ~21 trademark bulletins

## Strategy

1. Scrape patent rulings from `/fallos-relevantes-de-patentes/` (individual PDFs)
2. Scrape trademark bulletins from `/category/documentos/boletin-de-jurisprudencia-marcaria/` (quarterly PDFs)
3. Extract text from all PDFs using pdfplumber

## License

[Public Domain — Government of Chile](https://www.tdpi.cl/) — public court rulings. No restrictions on use.
