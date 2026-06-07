# UA/HACC — High Anti-Corruption Court of Ukraine (ВАКС)

Decisions of Ukraine's High Anti-Corruption Court (HACC / ВАКС), established April 2019.

## Data Source

Court decisions are sourced from the **Unified State Register of Court Decisions (ЄДРСР)** via the Ukraine Open Data portal (data.gov.ua). The scraper downloads yearly CSV ZIP archives and filters to HACC court codes:

- **4910**: HACC first instance
- **4911**: HACC Appeals Chamber (Апеляційна палата)

Full text is fetched from `od.reyestr.court.gov.ua` (open data subdomain, no CAPTCHA, no auth required).

## Coverage

- **Temporal**: April 2019 – present
- **Volume**: ~125K+ court documents
- **Language**: Ukrainian
- **Types**: Criminal cases involving corruption by high-ranking officials

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Open government data, attribution required.
