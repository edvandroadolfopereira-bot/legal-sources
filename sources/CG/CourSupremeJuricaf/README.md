# CG/CourSupremeJuricaf — Congo-Brazzaville Courts (Juricaf)

Court decisions from Congo-Brazzaville via the Juricaf database (AHJUCAF).

- **Source:** https://juricaf.org/recherche/+/facet_pays:Congo
- **Type:** case_law
- **Records:** 131 decisions (2000–2024)
- **Language:** French
- **Format:** HTML full text via Juricaf

## Courts Covered

- Cour suprême (Supreme Court)
- Cour d'appel de Brazzaville / Pointe-Noire (Courts of Appeal)
- Tribunal de commerce de Brazzaville / Pointe-Noire (Commercial Courts)

## Strategy

1. JSON API for paginated listing (`?format=json&page=N`)
2. Fetch individual decision pages for full text from `div#textArret`
3. Dublin Core metadata extracted from HTML `<meta>` tags

## License

[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) — attribution required, share-alike.
