# LK/PUCSL-Regulations — Public Utilities Commission of Sri Lanka

Official legal-document corpus published by the **Public Utilities Commission of
Sri Lanka (PUCSL)**, the multi-sector regulator responsible for Sri Lanka's
electricity industry (and related water/petroleum mandates).

- **Country:** Sri Lanka (LK)
- **Publisher:** PUCSL — https://www.pucsl.gov.lk/
- **Data type:** legislation (acts, regulations, codes, rules, tariff decisions & orders, guidelines, methodologies, policies, gazettes)
- **Auth:** none
- **Full text:** yes — extracted from PDFs via `pdfplumber`

## What it collects

PUCSL runs on WordPress and organises its legal corpus under the
`legal_documents_types` taxonomy. The custom `legal_documents` post type is **not**
exposed via the WP REST API, so the scraper reads the HTML archive pages for each
category:

```
/legal_documents_types/{acts, regulations, rules, codes, decisions_orders,
                         bst-and-unt, methodologies, guidelines, policies,
                         manuals, gazetts}/
```

Each document card carries a clean title (`.header-sm`), a year (`.year`), and a
link to a PDF in the site's media library (`wp-content/uploads/...`). The scraper
collects every card, dedupes by PDF URL across categories, downloads each PDF, and
extracts the full text. ~80 documents total, including the Sri Lanka Electricity
Acts (2002–2025), safety/quality/performance regulations, the grid & distribution
codes, bulk-supply and transmission tariff decisions, cost-reflective tariff
methodologies, licensing rules, and consumer-protection guidelines.

Captured fields: `title`, `text` (full body), `date` (publication year),
`category`, and the source `url`.

## Usage

```bash
python bootstrap.py bootstrap            # full pull (~80 docs)
python bootstrap.py bootstrap --sample   # sample records (writes sample/*.json)
python bootstrap.py test                 # connectivity test
```

## Notes

- Only the publication **year** is exposed on the archive cards, so `date` holds a
  four-digit ISO year (or null when absent).
- Archive pages are not paginated; each category page contains its full list.
- There is no incremental/changes API, so `update` re-fetches the full corpus.

## License

[Public Domain — Government of Sri Lanka official legal texts](https://www.pucsl.gov.lk/) —
acts, regulations, codes and regulatory decisions issued by the Public Utilities
Commission of Sri Lanka, published for public compliance. Sri Lanka has no formal
open-data licence; official statutes and regulatory instruments carry no copyright
restriction on reproduction. Commercial use permitted.
