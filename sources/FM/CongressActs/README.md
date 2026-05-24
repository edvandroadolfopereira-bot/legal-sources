# FM/CongressActs — FSM Congress Public Laws & Resolutions

Fetches enacted Public Laws and Congressional Resolutions from the official
Congress of the Federated States of Micronesia website (cfsm.gov.fm).

## Coverage

- **Public Laws**: 10th through 24th Congress (~600+ laws)
- **Resolutions**: 14th through 24th Congress (~800+ resolutions)

## Method

WordPress site hosting PDF documents. The scraper:
1. Crawls index pages for each congressional session
2. Extracts PDF download links
3. Downloads each PDF and extracts full text via `pdfplumber`

## License

[Open Government Data](https://www.cfsm.gov.fm/) — official FSM government
legislative documents, publicly available without restriction.
