# KZ/NationalBank — Kazakhstan National Bank Regulations

Regulatory acts (постановления) of the National Bank of the Republic of Kazakhstan,
including rules on banking, payments, securities, insurance, pensions, currency
regulation, digital assets, and financial stability.

- **Source:** adilet.zan.kz (Adilet Legal Information System)
- **Documents:** ~3,000+ registered regulatory acts
- **Language:** Russian, Kazakh
- **Full text:** Yes — extracted from HTML
- **Auth:** None required

## How it works

1. Lists NB documents via Adilet search filtered by organ code `kv=1_117`
2. Collects V-prefix document codes (Ministry of Justice registered acts)
3. Fetches each document's HTML from `adilet.zan.kz/rus/docs/{code}`
4. Extracts full text from the `container_gamma text text_new` div

## License

[Open Data — Ministry of Justice of Kazakhstan](https://adilet.zan.kz/) — government open data, no restrictions stated.
