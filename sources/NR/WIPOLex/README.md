# NR/WIPOLex — Nauru Legislation (WIPO Lex)

Full text of Nauru's statutes and regulations sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/en/members/profile/NR) database, WIPO's
free open gateway to the intellectual-property and IP-related laws of ~200
jurisdictions.

Nauru is a data-poor jurisdiction: PacLII (the historical Pacific legislation
gateway) now returns HTTP 410 behind a Cloudflare/ALTCHA anti-bot challenge to
datacenter and residential IPs alike, and ronlaw.gov.nr is intermittent. WIPO
Lex is a reliably reachable channel for machine-readable Nauru statute text.

## How it works

1. Fetch the server-rendered Nauru member profile, listing each legal text with
   its adoption date and a detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL (the
   signed `?last-modified=...` query string is required).
3. Download the PDF and extract full text via the shared `pdf_extract` backend.
   Scanned image-only PDFs with no text layer are skipped.

## Usage

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## Data

- `_type`: `legislation`
- Coverage: ~20 texts — Copyright Act 2019, Trademarks Act 2019, Patents
  Registration Act, and related regulations and rules.
- Language: English.

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of Nauru (acts, regulations, rules), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts. Commercial use OK.
