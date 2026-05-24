# KZ/ConstitutionalCouncil — Kazakhstan Constitutional Court & Council Decisions

Normative resolutions of the Constitutional Court (est. January 2023) and its
predecessor the Constitutional Council (1996–2022) of the Republic of Kazakhstan.

- **Source:** zan.gov.kz REST API (same backend as KZ/Adilet)
- **Documents:** ~94 normative resolutions (77 Court + 17 Council)
- **Language:** Russian, Kazakh
- **Full text:** Yes — structured content blocks via document detail API
- **Auth:** None required

## How it works

1. Searches the zan.gov.kz API for documents with `actTypes: ["НПОС"]`
   (normative resolutions)
2. Filters for Constitutional Court/Council decisions by checking if the
   `requisites` field contains "Конституционн" + "Суда" or "Совета"
3. Fetches full text for each decision via `GET /api/documents/{id}/rus`

## License

[Open Data — Ministry of Justice of Kazakhstan](https://zan.gov.kz/) — government open data, no restrictions stated.
