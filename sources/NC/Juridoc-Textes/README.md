# NC/Juridoc-Textes — New Caledonia Consolidated Legal Texts

Consolidated legal texts ("Textes consolidés") of New Caledonia published by the
Government of New Caledonia on [juridoc.gouv.nc](https://juridoc.gouv.nc/). The
collection contains the **Lois du pays**, the consolidated New Caledonian codes
(code civil applicable en NC, code du travail, code des impôts, etc.),
*délibérations* and other institutional texts.

## Data

- **~91 consolidated texts**, French language
- Full text extracted from **born-digital PDFs** (typically 4k–70k+ characters)
- Type: `legislation`

## Access

The site runs on Lotus Domino. The RSS view (`JdTextes.nsf/rss.xml`) is
enumerated via `?ReadViewEntries`, which returns one entry per document with an
embedded RSS `<item>` (title, PDF link, theme). Each PDF is downloaded and its
text extracted with PyMuPDF (`fitz`).

> **Host note:** published links use `www.juridoc.gouv.nc`, whose TLS certificate
> is only valid for the bare `juridoc.gouv.nc`. The scraper normalizes the host
> before downloading to avoid certificate-hostname-mismatch errors.

## Usage

```bash
python bootstrap.py test               # connectivity check
python bootstrap.py bootstrap --sample # 10+ sample records
python bootstrap.py bootstrap          # full pull → data/records.jsonl
python bootstrap.py bootstrap-fast     # alias used by the VPS pipeline
```

## License

> ⚠️ **Commercial use restricted.** Each PDF carries the notice
> *"Source : www.juridoc.gouv.nc - droits réservés de reproduction et
> réutilisation des données"* — reproduction and reuse rights are reserved by the
> Government of New Caledonia.

[Government of New Caledonia — Juridoc terms](https://juridoc.gouv.nc/) —
official legal texts of New Caledonia; attribution to juridoc.gouv.nc required,
commercial reuse not explicitly granted (flagged pending confirmation).
