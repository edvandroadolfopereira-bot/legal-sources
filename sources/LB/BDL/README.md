# LB/BDL — Banque du Liban

Central Bank of Lebanon circulars and regulations.

## Coverage

- **Basic Circulars**: ~189 major regulatory frameworks (banking, AML/CFT, capital adequacy, etc.)
- **Intermediate Circulars**: ~762 amendments and operational guidance
- **Period**: 1963–present
- **Language**: Arabic and English (varies by circular)

## How it works

1. Scrapes paginated listing pages for both circular types
2. Downloads PDFs using a constructed URL pattern (English preferred, Arabic fallback)
3. Extracts full text via pdfplumber

## License

[Lebanese Government Publication](https://www.bdl.gov.lb/disclaimer.php) — official central bank regulatory circulars published for public compliance. Attribution required.
