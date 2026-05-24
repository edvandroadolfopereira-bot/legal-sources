# CZ/RozhodnutiJustice — Czech Court Decisions Open Data

**Source:** [rozhodnutí.justice.cz](https://rozhodnuti.justice.cz)
**Country:** Czech Republic (CZ)
**Type:** Case law
**Records:** ~580,000 decisions (2020–present)

## Overview

Open data portal for Czech court decisions operated by the Ministry of Justice.
Covers all levels of the Czech judiciary below the apex courts:

- **Okresní soudy** (District Courts)
- **Krajské soudy** (Regional Courts)
- **Vrchní soudy** (High Courts)

This complements the existing CZ/SupremeCourt, CZ/ConstitutionalCourt, and
CZ/NSS sources which cover the three apex courts.

## API

Clean REST API with no authentication required:

| Endpoint | Returns |
|----------|---------|
| `/api/opendata` | Years with decision counts |
| `/api/opendata/{year}` | Months |
| `/api/opendata/{year}/{month}` | Days |
| `/api/opendata/{year}/{month}/{day}` | Decision listings (paginated) |
| `/api/finaldoc/{uuid}` | Full structured decision text |

Each decision includes ECLI identifier, court name, judge, case subject,
keywords, cited legal provisions, and full anonymized text (verdict + justification).

## License

[Open Government Data (Czech Republic)](https://rozhodnuti.justice.cz) — published under Act No. 106/1999 Sb. on free access to information. No restrictions on commercial use.
