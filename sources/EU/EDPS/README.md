# EU/EDPS — European Data Protection Supervisor Opinions

Fetches **EDPS Opinions** on EU legislative proposals, with full text extracted
from the published PDFs.

The European Data Protection Supervisor (EDPS) is the EU's independent data
protection authority for the Union institutions. Under Article 42 of Regulation
(EU) 2018/1725, the EU legislator must consult the EDPS on proposals with
data-protection implications. The resulting **Opinions** are the EDPS's formal,
public advice — a core corpus of EU data-protection doctrine.

## What it collects

- **Type:** `doctrine`
- **Coverage:** ~400 EDPS Opinions on EU regulations and directives.
- **Full text:** extracted from each opinion's English PDF.

## How it works

1. Scrapes the paginated [Opinions listing](https://www.edps.europa.eu/data-protection/our-work/our-work-by-type/opinions_en)
   (5 opinions per page, ~80 pages).
2. For each opinion, fetches the detail page and locates the English PDF under
   `/system/files/`.
3. Downloads the PDF and extracts text via the shared `common/pdf_extract`
   backend (pdfplumber/pypdf).
4. Normalizes to the standard schema. The publication date is taken from the
   opinion's URL slug (`YYYY-MM-DD-...`).

## Usage

```bash
python bootstrap.py test               # connectivity + one-PDF check
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap          # full run
```

## Schema

| Field    | Description                                   |
|----------|-----------------------------------------------|
| `_id`    | `EDPS-<slug>` from the opinion URL            |
| `_source`| `EU/EDPS`                                     |
| `_type`  | `doctrine`                                     |
| `title`  | Opinion title                                  |
| `text`   | Full text extracted from the opinion PDF       |
| `date`   | Publication date (ISO 8601)                    |
| `url`    | Opinion detail-page URL                        |
| `pdf_url`| Direct PDF URL                                 |

## License

[© European Union — reuse authorised (Commission Decision 2011/833/EU)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32011D0833) — EU institutional documents may be reused for commercial and non-commercial purposes; source acknowledgement is required and the reuse must not distort the original meaning.
