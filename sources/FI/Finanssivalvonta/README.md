# FI/Finanssivalvonta — Finnish Financial Supervisory Authority (FIN-FSA)

Supervision releases, administrative sanctions, penalty decisions, and public warnings
from the Finnish Financial Supervisory Authority (Finanssivalvonta / FIN-FSA).

## Data sources

1. **Supervision releases** (2013–2026): Regulatory guidance, inspection findings, rule
   amendments, and supervisory notices published yearly.
2. **Administrative sanctions** (2021–2026): Penalty payments, public warnings, and
   administrative fines listed on the supervisory measures page.

## Strategy

- Crawl yearly supervision-release index pages to discover article URLs
- Crawl the supervisory measures page for sanctions decision links
- Fetch each article page and extract full text from `<article>` tag
- Clean navigation/menu remnants from extracted text

## License

[Finnish Government Open Data](https://www.finanssivalvonta.fi/en/) — official
government supervisory decisions and regulatory communications. No explicit license
specified; treated as public domain government publications.
