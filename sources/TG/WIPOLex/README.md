# TG/WIPOLex — Togo Legislation (WIPO Lex)

Full text of the Togolese Republic's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Togo member profile lists the country's industrial-property and
copyright laws plus related commercial legislation: OAPI-related industrial
property texts (patents, trade marks, industrial designs), copyright and
neighbouring rights, customs, investment and related statutes. Texts are
predominantly in French (Togo's legislative language), with some English
translations.

## Why WIPO Lex

Togo has no comprehensive open legislation API or bulk download reachable from
outside the country; the official Journal Officiel is gazette-based. WIPO Lex
publishes machine-readable Togolese statute text without authentication and is a
stable external full-text source for the country's IP and commercial law.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/TG`) and parse each legal text's adoption
   date, title and detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL. The
   signed `?last-modified=...` query string is required. French is preferred,
   then English.
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
documents are official legislative texts of the Togolese Republic (laws, decrees,
orders), which are not subject to copyright. WIPO Lex republishes them free of
charge as a public gateway; no usage restriction is placed on the underlying
legal texts. Commercial use OK.
