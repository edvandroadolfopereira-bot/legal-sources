# DO/ProCompetencia — Comisión Nacional de Defensa de la Competencia (PRO-COMPETENCIA)

Full-text resolutions of the **Board of Directors (Consejo Directivo)** of the
Dominican Republic's national competition authority, the **Comisión Nacional de
Defensa de la Competencia (PRO-COMPETENCIA)**.

- **Country:** Dominican Republic (DO)
- **Publisher:** PRO-COMPETENCIA — https://procompetencia.gob.do/
- **Data type:** `case_law` (decisions of an administrative adjudicatory body)
- **Language:** Spanish (es)
- **Auth:** none

## What this covers

Resolutions issued under the **General Competition Law (Ley General de Defensa
de la Competencia, núm. 42-08)**, including:

- Merger / economic-concentration control decisions
- Abuse-of-dominance and anticompetitive-practice rulings
- Sanctioning procedures
- Hierarchical appeals (recursos jerárquicos) against the Executive Directorate
- Competition advocacy opinions and market studies
- Procedural resolutions deciding specific competition cases

~490 resolutions are published, dating from 2015 to the present.

## How it works

`procompetencia.gob.do` is a WordPress site. Each resolution is a post under the
custom post type `resoluciones-procompetencia`. The Yoast SEO sitemap
[`/resoluciones-pc-sitemap.xml`](https://procompetencia.gob.do/resoluciones-pc-sitemap.xml)
enumerates the entire corpus. For each post the scraper reads the `og:title`
(resolution title), the direct `/wp-content/uploads/.../*.pdf` link (the full
text), the `og:description` summary, and — on newer posts — the
`Fecha Publicación` field. Each PDF is downloaded and text-extracted with
**pdfplumber**.

The resolution's own adoption date is recovered from the closing formula
(*"...el día NUMBER (NN) de MES de AÑO (YYYY)"*), falling back to a numeric
dateline matching the resolution's year, then to the listing publication date.
A few of the oldest (2015) resolutions carry no machine-readable date and store
`null`.

## Usage

```bash
python bootstrap.py test                 # connectivity + single-doc check
python bootstrap.py bootstrap --sample   # 15 sample records
python bootstrap.py bootstrap            # full corpus
python bootstrap.py update               # incremental (by date)
```

## Output fields

`_id`, `_source`, `_type`, `_fetched_at`, `title`, `text` (full PDF text),
`date`, `url` (post page), `pdf_url`, `summary`, `doc_number`, `issuer`,
`jurisdiction`, `language`, `pdf_size`.

## License

Open Government Data (Dominican Republic) — official competition resolutions
published by a Dominican public institution (PRO-COMPETENCIA) on its
institutional website for public use. No license deed URL is published; the
documents are official acts of a state body in the public domain. Commercial
use permitted; attribution to PRO-COMPETENCIA appreciated.
