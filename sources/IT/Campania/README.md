# IT/Campania — Legislazione Regionale Campania

Regional laws (leggi regionali) of Campania, sourced from the **Normativa** section
of the Regione Campania website.

- **Coverage**: 2001–present (~1,844 laws)
- **Document types**: Leggi Regionali (LR)
- **Full text**: Yes — extracted from HTML pages (no PDF needed)
- **URL**: https://www.regione.campania.it/normativa/items.php?pgCode=G19I231&id_doc_type=1

## Strategy

1. Paginate through listing at `items.php?n_pagina=N&pgCode=G19I231&id_doc_type=1`
2. Extract item links (`item.php?pgCode=G19I231RXXXX&id_doc_type=1&id_tema=N`)
3. Fetch each individual law page
4. Extract full text from the `#document` div

## License

[Public domain — official acts (Art. 5, Legge 22 aprile 1941, n. 633)](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — regional laws are official acts of a public administration and are not protected by copyright under Italian law. Commercial use is permitted.
