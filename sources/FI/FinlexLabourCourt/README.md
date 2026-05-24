# FI/FinlexLabourCourt — Finland Labour Court Decisions

Finnish Labour Court (Työtuomioistuin) case law decisions via the Finlex Open Data REST API.

## Data

- **Type:** case_law
- **Volume:** ~6,700 decisions (1970–present)
- **Language:** Finnish
- **Full text:** Yes (Akoma Ntoso XML parsed to plain text)
- **Update frequency:** Hundreds of new decisions per year

## API

- **List endpoint:** `https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/doc/labour-court-decision/list?format=json`
- **Document endpoint:** `https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/doc/labour-court-decision/{year}/{number}/fin@`
- **Format:** JSON listing + Akoma Ntoso XML per document
- **Auth:** None (User-Agent header required)
- **Pagination:** `page` + `limit` (max 10 per page)

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Attribution required. Commercial use permitted.
