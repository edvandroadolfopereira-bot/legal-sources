# AZ/CBA-Regulations — Central Bank of Azerbaijan: Regulations & Decisions

Full-text English legal framework of the Central Bank of the Republic of
Azerbaijan (CBAR), published on [cbar.az](https://www.cbar.az/).

## What this source covers

Binding regulations, Management Board decisions, presidential decrees, cabinet
decrees and codes governing **Credit Institutions, Payments, Capital Market,
Currency regulation** and other areas supervised by CBAR, plus the bank's
**methodological documents**. Each act is published as a full-text HTML page at
`/law-{id}/{slug}`, carrying state-registration metadata (Ministry of Justice
registration number, approval/registration dates, approving Protocol).

- **Language:** English
- **Document types:** legislation (regulations/decisions/decrees/codes),
  doctrine (methodological documents)
- **Approx. volume:** ~98 full-text HTML acts

## Access method

No public API. The scraper walks the legal-framework listing pages
(`/page-{id}/x?language=en`) for each section and document kind, collects
`/law-{id}/{slug}` detail-page links, fetches each detail page, and extracts the
act body from `div.type_text` (HTML tags stripped, entities decoded). Pages that
yield fewer than 300 characters of extractable text (external/PDF-only "Laws"
pages) are skipped.

## Usage

```bash
python bootstrap.py bootstrap          # Full initial pull
python bootstrap.py bootstrap --sample # Fetch sample records for validation
python bootstrap.py update             # Incremental (recent acts)
```

## License

[Open Government Data](https://www.cbar.az/) — official legal texts of the
Central Bank of the Republic of Azerbaijan, published openly in English without
registration. No explicit machine-readable license is stated; treated as open
government data (public legal texts). Commercial use permitted.
