# BH/MOLA-Laws — Bahrain Ministry of Legal Affairs: Consolidated Laws

Consolidated laws and legislative decrees of the Kingdom of Bahrain, published
bilingually (English + Arabic) by the **Ministry of Legal Affairs (MoLA)**.

- **Listing:** https://www.mola.gov.bh/Legislation/Laws/
- **Source type:** legislation
- **Coverage:** ~58 consolidated laws & legislative decrees, full text
- **Languages:** English + Arabic (each PDF is bilingual)
- **Auth:** none

## How it works

The listing page exposes a structured HTML table; each row carries
`data-lawno`, `data-year`, `data-type`, `data-translation` attributes and a link
to the law's PDF (`/MediaManager/Media/Documents/Laws/...`). The scraper parses
the table, downloads each PDF, and extracts the full consolidated text with
PyMuPDF (`fitz`). Each PDF contains the full law text plus inline notes of any
subsequent amendments.

## Usage

```bash
python bootstrap.py test-api             # Connectivity / parse check
python bootstrap.py bootstrap --sample   # Fetch 15 sample records
python bootstrap.py bootstrap            # Full pull (~58 laws)
```

## Notes

This site previously returned HTTP 403 to the project (see issue #822) and was
marked blocked; as of 2026-06-11 it serves the listing and PDFs normally. Unlike
`BH/MIA-Gazette` (gazette *issues*), this source provides individual
**consolidated law texts** with official English translations, which are more
directly useful for legal retrieval.

## License

[Bahrain Government Open Data](https://www.data.gov.bh/en/ODPolicy) — official
government legislation published by the Ministry of Legal Affairs; open access,
commercial use permitted with attribution.
