# IN/APTEL — Appellate Tribunal for Electricity

Judgments and orders from the Appellate Tribunal for Electricity (APTEL), India.

APTEL hears appeals against orders of the Central Electricity Regulatory Commission
(CERC), State Electricity Regulatory Commissions (SERCs), and the Petroleum and
Natural Gas Regulatory Board (PNGRB).

- **Coverage:** 2008–present (~3,000 judgments/orders)
- **Format:** PDF judgments with selectable text
- **Access:** Public, no authentication required
- **Source URL:** https://aptel.gov.in/en/old-judgement-data

## Strategy

1. Scrape the judgment listing page filtered by year (2008–2026)
2. Extract case metadata (serial number, case number, cause title, bench, date)
3. Download each PDF and extract full text using pdfplumber
4. Normalize into standard schema with full text

## License

[Government of India Open Data](https://aptel.gov.in/) — Indian tribunal decisions are public records. Attribution recommended.
