# TW/LYGazette — Taiwan Legislative Yuan Gazette

Official gazette of the Taiwan Legislative Yuan (立法院公報), containing
full-text parliamentary proceedings, committee reports, bill readings,
interpellations, and meeting minutes.

## Data source

- **API**: https://v2.ly.govapi.tw/ (g0v community API)
- **Coverage**: ~2,200+ gazette issues with multiple agenda items each
- **Format**: JSON metadata + plain text content
- **Language**: Traditional Chinese (繁體中文)

## Strategy

1. Paginate through gazette issues via `/gazettes`
2. For each gazette, fetch agenda items via `/gazette/{id}/agendas`
3. For each agenda with text URLs, fetch full text from `/gazette_agenda_doc/{id}/txt`
4. Each agenda item becomes a separate record

## License

[Taiwan Open Government Data License](https://data.gov.tw/en) — attribution required.
