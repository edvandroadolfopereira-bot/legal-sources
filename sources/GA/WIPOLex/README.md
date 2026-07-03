# GA/WIPOLex — Gabon Legislation (WIPO Lex)

Full text of the Republic of Gabon's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Gabon member profile lists the country's industrial-property and
copyright acts and regulations, plus related commercial law: patents, trade
marks, copyright and neighbouring rights, and related statutes. Most texts are
in French (Gabon's legislative language).

## Why WIPO Lex

Gabon has no comprehensive open legislation API, bulk download or free LII-style
platform reachable from outside the country; what exists (the Journal Officiel
and ministry portals) is either offline-only, paywalled or unreliable from
datacenter IPs. WIPO Lex publishes machine-readable Gabon statute text without
authentication and is a stable, commercially-usable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/GA`) and parse each legal text's adoption
   date, title and detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL. The
   signed `?last-modified=...` query string is required. French is preferred.
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
documents are official legislative texts of the Republic of Gabon (acts,
regulations, decrees), which are not subject to copyright. WIPO Lex republishes
them free of charge as a public gateway; no usage restriction is placed on the
underlying legal texts. Commercial use OK.
