# GN/CourSupremeJuricaf — Guinea Courts (Juricaf)

Court decisions from Guinea via the Juricaf database (AHJUCAF).

- **Source:** https://juricaf.org/recherche/+/facet_pays:Guinée
- **Type:** case_law
- **Records:** 128 decisions
- **Language:** French
- **Format:** HTML full text via Juricaf

## Courts Covered

- Cour suprême (Supreme Court) — 126 decisions
- Cour d'appel (Court of Appeal) — 2 decisions

## Strategy

1. JSON API for paginated listing (`?format=json&page=N`)
2. Fetch individual decision pages for full text from `div#textArret`
3. Dublin Core metadata extracted from HTML `<meta>` tags

## License

[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) — attribution required, share-alike.
