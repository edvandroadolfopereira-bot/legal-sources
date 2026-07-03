# NC/Juridoc-Juris — New Caledonia Jurisprudence

Jurisprudence of New Caledonia published by the Government of New Caledonia on
[juridoc.gouv.nc](https://juridoc.gouv.nc/) — chiefly decisions of the **Tribunal
administratif de Nouvelle-Calédonie**, plus occasional **Conseil d'État** rulings
concerning New Caledonia.

## Data

- **~103 decisions**, French language
- Full text extracted from **born-digital PDFs** (typically 3k–12k characters)
- Type: `case_law`
- Parsed metadata: court, decision number, date, *matière* (subject)

## Access

The site runs on Lotus Domino. The RSS view (`JdJuris.nsf/rss.xml`) is enumerated
via `?ReadViewEntries`, which returns one entry per decision with an embedded RSS
`<item>` (title, PDF link, matière). Each PDF is downloaded and its text extracted
with PyMuPDF (`fitz`).

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
official jurisprudence of New Caledonia; attribution to juridoc.gouv.nc required,
commercial reuse not explicitly granted (flagged pending confirmation).
