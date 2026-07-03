# LS/WIPOLex — Lesotho Legislation (WIPO Lex)

Full text of Lesotho's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for Lesotho

Lesotho's national legal-information sites are unreliable from outside the
country: the LesothoLII and Laws.Africa platforms residential-block / rate-limit
external datacenter IPs (`LS/LawsAfrica` is blocked for this reason). WIPO Lex
publishes machine-readable Lesotho statute text without authentication, and is a
stable external full-text source complementing the existing LS sources.

## Coverage

17 Lesotho legal texts are listed on the WIPO Lex member profile, with
extractable English text layers. Documents include:

- Industrial-property / intellectual-property acts and orders
- Copyright law
- Commercial, company and investment statutes
- and related IP/IP-adjacent acts

Texts are in English (Lesotho's legislative language).

## How it works

1. Fetch the server-rendered LS member profile
   (`/wipolex/en/members/profile/LS`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/ls/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page. English is preferred, then French.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of the Kingdom of Lesotho (acts, codes, orders), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
