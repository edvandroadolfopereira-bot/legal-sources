# TT/e-Gazette — Trinidad & Tobago Official Gazette (Government Printery)

Collects full-text **legislation** from the Republic of Trinidad & Tobago's
official e-Gazette, published by the Government Printery at
<https://printery.gov.tt/e-gazette/>.

## What it collects

- **Acts of Parliament** (enacted laws and bills) — `Acts/` folder per year
- **Legal Notices** (statutory instruments / subsidiary legislation) — `Legal Notices/` folder per year

Documents are published as per-document, digital-native (text-extractable) PDFs
organized in an open Apache directory listing by year. The scraper walks the
year index, lists the `Acts` and `Legal Notices` folders, downloads each PDF,
and extracts the full text. PDFs yielding fewer than 400 characters of
extractable text (e.g. older scanned compilations) are skipped — no OCR.

## Access method

No public API. Open directory listing (HTML) + per-document PDF download.
Rate limited to ~1 request/second.

## Fields

`_id`, `_source`, `_type`, `_fetched_at`, `title`, `text` (full document body),
`date`, `url`, `pdf_url`, `document_number`, `category`, `year`, `language`,
`jurisdiction`.

## License

[Open Government Data](https://printery.gov.tt/) — Acts of Parliament and Legal
Notices of Trinidad & Tobago are official government legal texts published
openly by the Government Printery without registration. No explicit
machine-readable license is stated; treated as open government data (public
legal texts). Commercial use permitted.
