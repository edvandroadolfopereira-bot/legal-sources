# AR/MPF-Dictamenes — Ministerio Público Fiscal Dictámenes

Attorney General (Procurador General de la Nación) opinions before Argentina's
Supreme Court. Over 55,000 dictámenes from 1919 to present, covering
constitutional, criminal, civil, labor, and administrative law.

## Data Access

- **Method**: HTML scraping + PDF download & extraction
- **Search portal**: https://www.mpf.gob.ar/buscador-dictamenes/
- **Auth**: None required
- **Format**: PDFs at `/dictamenes/YEAR/AUTHOR/MONTH/FILENAME.pdf`
- **Pagination**: `?pag=N&cant=10` URL parameters

## Fields

| Field | Description |
|-------|-------------|
| `text` | Full text extracted from PDF via pdfplumber |
| `sumario` | Summary from the search results HTML |
| `title` | Subject matter keywords |
| `prosecutor` | Name of the signing prosecutor |
| `date` | Approximate date from PDF path (YYYY-MM-01) |
| `pdf_filename` | Original PDF filename |

## License

[Public Domain — Argentine Government Official Acts](https://www.mpf.gob.ar/) — government legal opinions are public domain under Argentine law.
