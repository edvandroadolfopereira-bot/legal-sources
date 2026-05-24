# BZ/SupremeCourt — Belize Supreme Court Judgments

Fetches Supreme Court judgments from the Judiciary of Belize website.

- **Source**: https://judiciary.bz/judgements2/
- **Type**: case_law
- **Coverage**: Criminal (1977–2022), Civil (1972–2022)
- **Format**: PDF (text extracted via pdfplumber)
- **Language**: English

## How it works

1. Parses the main judgments page to find year-based sub-pages
2. Splits links into Criminal and Civil sections (detected by duplicate years)
3. Extracts PDF links from each year page
4. Downloads PDFs and extracts full text using pdfplumber
5. Normalizes into standard schema with case metadata

## License

[Public Domain](https://www.wipo.int/wipolex/en/legislation/details/3920) — Official government court decisions in Belize are public domain.
