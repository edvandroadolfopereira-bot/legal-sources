# FI/FinlexAdminCourts — Finnish Administrative Courts Decisions

Fetches decisions from Finland's six administrative courts (hallinto-oikeudet) via
the Finlex website's Next.js RSC endpoint. Covers decisions from 1981 to present.

## Courts

| Slug | Finnish Name | English Name |
|------|-------------|--------------|
| helsinki | Helsingin hallinto-oikeus | Helsinki Administrative Court |
| hameenlinna | Hämeenlinnan hallinto-oikeus | Hämeenlinna Administrative Court |
| ita-suomi | Itä-Suomen hallinto-oikeus | Eastern Finland Administrative Court |
| pohjois-suomi | Pohjois-Suomen hallinto-oikeus | Northern Finland Administrative Court |
| turku | Turun hallinto-oikeus | Turku Administrative Court |
| vaasa | Vaasan hallinto-oikeus | Vaasa Administrative Court |

## Data Access

- **Method**: Finlex Next.js React Server Components (RSC) endpoint
- **Year listing**: `GET /fi/oikeuskaytanto/hallinto-oikeudet/{year}` with `RSC: 1` header
- **Case page**: `GET /fi/oikeuskaytanto/hallinto-oikeudet/{year}/{court}/{number}` with `RSC: 1` header
- **Full text**: Extracted from `highlightable` spans in RSC response
- **Auth**: None required
- **Coverage**: 1981–present, ~40–100 decisions/year, ~2000+ total

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Finlex Open Data, attribution required.
