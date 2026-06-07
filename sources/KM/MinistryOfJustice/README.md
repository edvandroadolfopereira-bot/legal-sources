# KM/MinistryOfJustice — Comoros Ministry of Justice (Legislation)

Official legislation portal of the **Ministère de la Justice de l'Union des
Comores** ([justice.gouv.km](https://justice.gouv.km/)). Publishes the
consolidated body of Comorian law — *lois, décrets, ordonnances, codes* and
*arrêtés* — from the colonial era (early 1900s) through 2025.

## Data access

- **Enumeration:** the Yoast text sitemap
  [`/texte-sitemap1.xml`](https://justice.gouv.km/texte-sitemap1.xml) lists
  ~330 documents (each `<loc>` + `<lastmod>`).
- **Full text per document:** each `/texte/{slug}/` page carries the body
  either **inline** in `<div class="the-content">` *or* as a linked **PDF**
  under `/wp-content/uploads/`. The scraper takes whichever is longer.
- No API key or authentication required.

### Notable quirks

- Pages render **two** `div.the-content` nodes (one empty placeholder, one
  filled) — the scraper always selects the longest.
- PDF URLs contain `°` and accented characters; they are percent-encoded
  before download.
- Some older PDFs are **scanned images with no text layer**; these are
  skipped (no OCR). ~85% of documents yield clean full text.
- Language: **French**.

## Fields

`_id`, `_source`, `_type` (`legislation`), `_fetched_at`, `title`, `text`
(full body), `date` (ISO 8601, parsed from the French date in the title;
`null` when absent), `url`, `doc_type` (`loi`/`décret`/`ordonnance`/`code`/
`arrêté`/`autre`), `text_source` (`inline`/`pdf`), `pdf_url`, `language`,
`slug`.

## Usage

```bash
python bootstrap.py test                       # connectivity + 1 sample doc
python bootstrap.py bootstrap --sample          # 12 sample records
python bootstrap.py bootstrap                    # full pull (~330 docs)
python bootstrap.py bootstrap-fast               # concurrent full pull
```

## License

[Public domain — official government legal texts](https://justice.gouv.km/) — no attribution required.

The site publishes no explicit reuse licence. Comorian official legal texts
(*lois, décrets, ordonnances, codes*) are **edicts of government** and are not
subject to copyright under the edict-of-government doctrine. Treated as public
domain; **commercial use permitted**.
