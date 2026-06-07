# IT/Sardegna — Legislazione Regionale Sardegna

Regional laws (leggi regionali) of the Autonomous Region of Sardinia, sourced
from the official **Banca dati giuridica** maintained by the Regione Autonoma
della Sardegna.

- **Coverage**: 1949–present (~2600 laws)
- **Document types**: Leggi Regionali (LR)
- **Full text**: Yes — extracted from PDF downloads via REST API
- **URL**: https://leggiregionali.regione.sardegna.it/

## Strategy

1. Paginate through the REST search API (`/regional-laws/front-office/search`)
2. For each law, download the PDF (`/front-office/{id}/files/pdf`)
3. Extract full text from PDF using pdfplumber
4. Normalize to standard schema

## License

[Public domain — official acts (Art. 5, Legge 22 aprile 1941, n. 633)](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — regional laws are official acts of a public administration and are not protected by copyright under Italian law. Commercial use is permitted.
