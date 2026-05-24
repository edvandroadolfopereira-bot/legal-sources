# LR/LRA-Laws — Liberia Revenue Authority Tax and Customs Laws

Fetches tax legislation, customs codes, executive orders, and administrative
regulations from the Liberia Revenue Authority website.

## Data

- **Source**: https://revenue.lra.gov.lr/laws-issuances/
- **Type**: legislation
- **Format**: PDF documents linked from a single HTML listing page
- **Language**: English
- **Volume**: ~65 documents

## Categories

- Revenue Code & Amendments
- Customs Tariffs
- Executive Orders
- Administrative Regulations
- Related Laws (LRA Act, Public Procurement Act, etc.)

## Strategy

1. Scrape the listing page for PDF links and titles
2. Download each PDF and extract text with pdfplumber
3. Categorize by section (revenue code, tariff, executive order, regulation, other)

## License

[Public Domain — Government of Liberia](https://revenue.lra.gov.lr/laws-issuances/) — official legislation published for public access. No restrictions on use.
