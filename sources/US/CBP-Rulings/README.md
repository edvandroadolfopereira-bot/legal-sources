# US/CBP-Rulings — Customs and Border Protection Rulings (CROSS)

The **Customs Rulings Online Search System (CROSS)** contains 220,000+ binding rulings, internal advice memoranda, and headquarters rulings letters issued by U.S. Customs and Border Protection. Rulings cover tariff classification, valuation, country of origin, marking, and other trade issues dating back to 1989.

**URL:** https://rulings.cbp.gov/

## Data Access

JSON API at `rulings.cbp.gov/api/`:
- `GET /api/search?term=...&sortBy=date&page=N&pageSize=100` — paginated search
- `GET /api/ruling/{rulingNumber}` — individual ruling with full text
- `GET /api/stat/lastupdate` — database statistics

No authentication required.

## License

[Public Domain (US Government Work)](https://www.law.cornell.edu/uscode/text/17/105) — CBP rulings are works of the US federal government, not subject to copyright under 17 USC § 105.
