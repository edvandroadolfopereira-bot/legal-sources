# CL/NicChile — NIC Chile Domain Dispute Rulings

Fetches arbitration rulings from NIC Chile's online dispute resolution
system for .cl domain names.

## Data

- **Source**: https://www.nic.cl/rcal/fallos.do
- **Type**: case_law
- **Format**: JSON API with PDF full text downloads
- **Language**: Spanish
- **Volume**: ~15,000+ rulings

## Strategy

1. Paginate through `sentenciasArbitrales.do` JSON API (30 records/page)
2. For each ruling, download the PDF via `downloadResolucion.do?uuid=<uuid>`
3. Extract text from PDF using pdfplumber

## License

[Public Domain — Government of Chile](https://www.nic.cl/rcal/fallos.do) — public arbitration rulings. No restrictions on use.
