# IT/Basilicata — Legislazione Regionale Basilicata

Regional laws (leggi regionali) of the Basilicata Region, published by the
Consiglio Regionale della Basilicata.

- **Source**: https://atticonsiglio.consiglio.basilicata.it/AD_Elenco_Leggi
- **Coverage**: 1971–present (~2350 laws)
- **Type**: legislation
- **Format**: HTML (consolidated/coordinated text)

## Strategy

Each law is served at a stable URL using an internal database ID:
`/AD_Elenco_Leggi?Codice=N` (N = 1 to ~2389). The scraper enumerates all
Codice values, extracts full text from the `WordSection1` container, and
parses metadata (law number, date, title, Bollettino reference) from the
document header.

## License

[Public domain — Art. 5 L. 633/1941](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — Italian regional laws are official acts not protected by copyright.
