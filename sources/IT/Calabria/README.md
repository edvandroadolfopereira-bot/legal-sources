# IT/Calabria — Legislazione Regionale Calabria

Regional laws (leggi regionali) of Calabria, sourced from the **Banche Dati**
of the Consiglio Regionale della Calabria.

- **Coverage**: 1971–present
- **Document types**: Leggi Regionali (LR)
- **Full text**: Yes — extracted from PDF downloads
- **URL**: https://www.consiglioregionale.calabria.it/portale/BancheDati/Leggi/LeggiForm

## Strategy

1. POST search form by year (`/BancheDati/Leggi/Leggi?pagerOff=True`)
2. Parse HTML response for law metadata and PDF links
3. Download each PDF from `/bdf/api/BDF?numero=N&anno=YEAR`
4. Extract full text using pdfplumber

## License

[Public domain — official acts (Art. 5, Legge 22 aprile 1941, n. 633)](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — regional laws are official acts of a public administration and are not protected by copyright under Italian law. Commercial use is permitted.
