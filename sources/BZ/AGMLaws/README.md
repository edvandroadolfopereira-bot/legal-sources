# Belize Consolidated Laws (Attorney General's Ministry)

**Source:** [https://www.agm.gov.bz/laws/](https://www.agm.gov.bz/laws/)
**Country:** BZ
**Data types:** legislation
**Language:** English

## Description

Official legislation from the Attorney General's Ministry of Belize. Covers:
- **Substantive Laws** (Revised Edition 2020) — 18 volumes, ~413 consolidated laws
- **Subsidiary Laws** (R.E. 2020) — ~252 regulations
- **Annual Acts** (2021–2026) — ~198 new acts
- **Statutory Instruments** (2021–2026) — ~842 instruments

Total: ~1,700 legal instruments.

## How it works

1. Calls `POST /api-laws/` with action and volume parameters to get JSON lists
2. Parses HTML links from the API response to get PDF URLs
3. Downloads each PDF and extracts text with pdfplumber
4. Normalizes into the standard schema with full text

## License

[Public Domain — Government of Belize](https://www.agm.gov.bz/) — official government legislation published for public access.
