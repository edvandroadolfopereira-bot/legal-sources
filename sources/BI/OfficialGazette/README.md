# BI/OfficialGazette — Burundi Official Gazette (Bulletin Officiel du Burundi)

Laws, decrees and ordonnances of the Republic of Burundi, published by the
**Service chargé de la législation** on the official portal
[amategeko.gov.bi](https://amategeko.gov.bi) ("amategeko" = "laws" in Kirundi).

## What it fetches

- **Type:** legislation (laws, decrees, ministerial ordonnances, administrative decisions)
- **Coverage:** ~2000 individual acts enumerated via the WordPress sitemap for
  the `laws_and_other_acts` custom post type.
- **Full text:** YES. Each act's detail page is metadata-only and links to the
  consolidated **Bulletin Officiel du Burundi (BOB)** PDF for that issue. The
  BOB PDFs contain **selectable text** (not scanned images), so the full body
  of each act is extracted directly. Texts are published bilingually in
  **French and Kirundi**.

## How it works

1. `GET /wp-sitemap-posts-laws_and_other_acts-1.xml` → list of act detail URLs.
2. For each act, parse the detail page for title, act number, date, BOB number,
   status, and the link to the BOB PDF (`...BOB-NoXXX.pdf#page=N`, where `N` is
   the gazette page number under the BOB's continuous numbering).
3. Download the BOB PDF and split it into acts using the headings that delimit
   each text, e.g. `LOI N°1/04 DU 29/01/2018 ...`, `DECRET N°100/197 DU ...`,
   `ORDONNANCE MINISTERIELLE N°610/1194 DU ...`. The act whose number matches the
   detail page is extracted; a gazette-page lookup is used as a fallback.
4. Page headers/footers (`BOB N°...`) and standalone gazette page numbers are
   stripped from the extracted text.

BOB PDFs are cached (LRU) so that multiple acts from the same issue are not
re-downloaded.

### Note on the REST API

The site runs WordPress but its `/wp-json/` REST API is blocked by a security
plugin (returns HTTP 420). The public XML sitemap + HTML detail pages + PDF
extraction are used instead — no authentication required.

## Usage

```bash
python bootstrap.py test                 # verify sitemap + one act extraction
python bootstrap.py bootstrap --sample   # 15 sample records
python bootstrap.py bootstrap --full     # all acts
```

## License

[Public domain (government)](https://amategeko.gov.bi) — official legal texts
(laws, decrees, ordonnances) enacted and published by the Government of Burundi.
Government edicts and legislation are not subject to copyright. Commercial use
permitted; no attribution required.
