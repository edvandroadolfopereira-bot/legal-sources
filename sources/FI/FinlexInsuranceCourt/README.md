# FI/FinlexInsuranceCourt — Finland Insurance Court Decisions

Vakuutusoikeus (Insurance Court) decisions from Finlex, Finland's official legal database.

- **URL**: https://www.finlex.fi/fi/oikeuskaytanto/vakuutusoikeus
- **Coverage**: 1957–present
- **Documents**: ~1,500-2,000 selected insurance court decisions
- **Language**: Finnish
- **Data type**: case_law
- **Full text**: Yes — extracted from Next.js RSC payload (highlightable spans)

## Access Method

HTML scraping of Finlex Next.js SPA:
1. Fetch year index pages to discover decision URLs
2. Fetch individual decision pages
3. Extract full text from embedded RSC (React Server Components) data

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Finlex open data, attribution required.
