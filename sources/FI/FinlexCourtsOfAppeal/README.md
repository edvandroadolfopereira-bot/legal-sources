# FI/FinlexCourtsOfAppeal — Finnish Courts of Appeal Decisions

Fetches decisions from Finland's five courts of appeal (hovioikeudet) via
the Finlex website's Next.js RSC endpoint. Covers decisions from 1964 to present.

## Courts

| Slug | Finnish Name | English Name |
|------|-------------|--------------|
| helsinki | Helsingin hovioikeus | Helsinki Court of Appeal |
| ita-suomi | Itä-Suomen hovioikeus | Eastern Finland Court of Appeal |
| turku | Turun hovioikeus | Turku Court of Appeal |
| vaasa | Vaasan hovioikeus | Vaasa Court of Appeal |
| rovaniemi | Rovaniemen hovioikeus | Rovaniemi Court of Appeal |

## Data Access

- **Method**: Finlex Next.js React Server Components (RSC) endpoint
- **Year listing**: `GET /fi/oikeuskaytanto/hovioikeudet/{year}` with `RSC: 1` header
- **Case page**: `GET /fi/oikeuskaytanto/hovioikeudet/{year}/{court}/{number}` with `RSC: 1` header
- **Full text**: Extracted from `highlightable` spans in RSC response
- **Auth**: None required
- **Coverage**: 1964–present, thousands of decisions

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Finlex Open Data, attribution required.
