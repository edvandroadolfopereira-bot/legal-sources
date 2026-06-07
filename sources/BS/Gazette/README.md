# BS/Gazette — Bahamas Official Gazette

Official Gazette of the Commonwealth of The Bahamas, published by authority.

**URL:** https://laws.bahamas.gov.bs/cms/gazettes/gazettes-by-year.html

## Coverage

- **Years:** 2021–present
- **Content:** Government proclamations, appointments, price controls, trade union registrations, land acquisition notices, and other official announcements
- **Format:** PDF with extractable text
- **Volume:** ~200+ gazette entries across available years

## Data Collection

The scraper:
1. Iterates through available years (2021–present) via form POST
2. Extracts gazette PDF links and titles from the HTML response
3. Downloads each PDF and extracts full text using pdfplumber/pdfminer
4. Normalizes records with title, full text, date, and source URL

## License

[Public domain (government)](https://laws.bahamas.gov.bs/cms/?view=article&id=115:copyright&catid=14:general-articles) — official government publications.
