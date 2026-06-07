# IT/Puglia — Legislazione Regionale Puglia

Regional laws (leggi regionali) and regulations (regolamenti regionali) of the
Puglia region, sourced from the **Bussola Normativa** database maintained by the
Consiglio Regionale della Puglia.

- **Coverage**: 1972–present
- **Document types**: Leggi Regionali (LR), Regolamenti Regionali (RR)
- **Full text**: Yes — extracted from HTML detail pages
- **URL**: https://bussolanormativa.consiglio.puglia.it/

## Strategy

1. Year-by-year search via ASP.NET POST form at `RicercaSemplice.aspx`
2. Paginate through results (20 per page) using `__doPostBack` pagination
3. Fetch each law's detail page at `LeggeNavscroll.aspx?id=<ID>`
4. Extract full text from the `it-page-sections-container` div

## License

[Public domain — official acts (Art. 5, Legge 22 aprile 1941, n. 633)](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — regional laws are official acts of a public administration and are not protected by copyright under Italian law. The Bussola Normativa site declares no specific reuse licence; commercial use is permitted.
