# FI/FinlexMarketCourt — Finnish Market Court Decisions

Fetches decisions from Finland's Market Court (markkinaoikeus) via
the Finlex website's Next.js RSC endpoint. Competition, procurement,
and IP cases from 1979 to present.

## Data Access

- **Method**: Finlex Next.js React Server Components (RSC) endpoint
- **Year listing**: `GET /fi/oikeuskaytanto/markkinaoikeus/{year}` with `RSC: 1` header
- **Case page**: `GET /fi/oikeuskaytanto/markkinaoikeus/{year}/{number}` with `RSC: 1` header
- **Full text**: Extracted from `highlightable` spans in RSC response
- **Auth**: None required
- **Coverage**: 1979–present, thousands of decisions

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Finlex Open Data, attribution required.
