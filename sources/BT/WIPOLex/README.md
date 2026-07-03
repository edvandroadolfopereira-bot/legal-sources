# BT/WIPOLex — Bhutan Legislation (WIPO Lex)

Full text of the Kingdom of Bhutan's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Bhutan member profile lists the country's copyright and
industrial-property acts plus related legislation: civil and criminal codes,
companies and contract acts, customs and other commercial statutes. Texts are in
English (Bhutan enacts its statutes in English alongside Dzongkha).

## Why WIPO Lex

Bhutan has no comprehensive open legislation API reachable from outside the
country; the National Assembly and the official Depository of Laws portals block
or rate-limit datacenter traffic (both are blocked in this repo for that reason).
WIPO Lex publishes machine-readable Bhutanese statute text in English without
authentication and is a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/BT`) and parse each legal text's adoption
   date, title and detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL. The
   signed `?last-modified=...` query string is required. English is preferred,
   then French.
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
documents are official legislative texts of the Kingdom of Bhutan (acts, rules,
codes), which are not subject to copyright. WIPO Lex republishes them free of
charge as a public gateway; no usage restriction is placed on the underlying
legal texts. Commercial use OK.
