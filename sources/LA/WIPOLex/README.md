# LA/WIPOLex — Laos Legislation (WIPO Lex)

Full text of the Lao People's Democratic Republic's intellectual-property and
IP-related laws from the **WIPO Lex** database (https://www.wipo.int/wipolex/),
WIPO's free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Laos member profile lists the country's intellectual-property law
plus related legislation: civil and penal codes, contract law, enterprise and
investment law, customs and other commercial statutes. Texts are in English
(WIPO's official translations of the Lao originals).

## Why WIPO Lex

Laos has no comprehensive open legislation API reachable from outside the
country; the national gazette and assembly portals block or rate-limit datacenter
traffic (several LA sources in this repo are blocked for that reason). WIPO Lex
publishes machine-readable Lao statute text in English without authentication and
is a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/LA`) and parse each legal text's adoption
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
documents are official legislative texts of the Lao People's Democratic Republic
(laws, decrees, ordinances), which are not subject to copyright. WIPO Lex
republishes them free of charge as a public gateway; no usage restriction is
placed on the underlying legal texts. Commercial use OK.
