# YE/WIPOLex — Yemen Legislation (WIPO Lex)

Full text of Yemen's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for Yemen

Yemen has no comprehensive open legislation API or database reachable from
outside the country; years of conflict have left its official
legal-publication infrastructure offline or unreliable. WIPO Lex publishes
machine-readable Yemeni statute text without authentication, and is one of the
very few stable full-text sources of Yemeni law available externally.

## Coverage

21 Yemeni legal texts are listed on the WIPO Lex member profile, most with
extractable text layers (mostly Arabic, some English). Documents include:

- Industrial-property / intellectual-property laws and codes
- Copyright and related-rights law
- Commercial, customs and investment statutes
- and related IP/IP-adjacent acts

Texts are in Arabic where available, then English, then French.

## How it works

1. Fetch the server-rendered YE member profile
   (`/wipolex/en/members/profile/YE`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/ye/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page. Arabic is preferred, then English, then French.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of the Republic of Yemen (laws, codes, decrees), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
