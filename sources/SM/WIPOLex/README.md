# SM/WIPOLex — San Marino Legislation (WIPO Lex)

Full text of the Republic of San Marino's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex San Marino member profile lists the country's IP and related law:
the Industrial Property Consolidation Law, the Protection of Copyright Law, and
numerous council decrees ratifying international IP and related instruments. All
texts are in Italian (San Marino's legislative language).

## Why WIPO Lex

San Marino has domestic legislation portals (Bollettino Ufficiale,
Legisammarino) but no open bulk download or API reachable from outside the
microstate. WIPO Lex publishes machine-readable San Marino statute text without
authentication and is a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/SM`) and parse each legal text's adoption date,
   title and detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL. The
   signed `?last-modified=...` query string is required.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.
   Scanned image-only PDFs with no text layer are skipped.

## Usage

```bash
python bootstrap.py test            # verify profile + detail + PDF reachable
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the
documents are official legislative texts of the Republic of San Marino (laws,
decrees, council decrees), which are not subject to copyright. WIPO Lex
republishes them free of charge as a public gateway; no usage restriction is
placed on the underlying legal texts. Commercial use OK.
