# HN/TSC-Biblioteca — Honduras TSC Virtual Library

Legislation from the **Tribunal Superior de Cuentas** (TSC) Biblioteca Virtual.

- **URL:** https://www.tsc.gob.hn/biblioteca/index.php/leyes
- **Coverage:** ~300 Honduran laws including the Constitution, codes, and decrees
- **Format:** PDFs downloaded and text-extracted via pdfplumber
- **Language:** Spanish

## How it works

1. Scrapes paginated HTML list pages (25 pages, 12 items each)
2. Extracts PDF download URLs from each entry
3. Downloads PDFs and extracts full text via pdfplumber
4. Parses publication dates from La Gaceta headers

## License

[Honduras Government Publications](https://www.tsc.gob.hn/biblioteca/) — official government legislation, public domain.
