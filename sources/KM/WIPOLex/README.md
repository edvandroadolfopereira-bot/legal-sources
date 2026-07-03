# KM/WIPOLex — Comoros Legislation (WIPO Lex)

Full text of the Comoros's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for the Comoros

The Comoros has no comprehensive open legislation portal reachable from outside
the country. WIPO Lex publishes machine-readable Comorian statute text without
authentication, complementing the existing KM sources.

## Coverage

11 Comorian legal texts are listed on the WIPO Lex member profile, with
extractable text layers (mostly French, one English). Documents include:

- Industrial-property / intellectual-property laws and codes
- Copyright law
- Commercial and investment statutes
- and related IP/IP-adjacent acts

Texts are in French where available, then English, then Arabic.

## How it works

1. Fetch the server-rendered KM member profile
   (`/wipolex/en/members/profile/KM`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/km/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page. French is preferred, then English, then Arabic.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of the Union of the Comoros (laws, codes, decrees), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
