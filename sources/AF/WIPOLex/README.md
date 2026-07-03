# AF/WIPOLex — Afghanistan Legislation (WIPO Lex)

Full text of Afghanistan's framework legislation, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for Afghanistan

Afghanistan is one of the project's most data-poor jurisdictions. Every native
government legislation portal is blocked for full-text collection:

- **laws.af (ACKU)** — catalog/index only, no document body
- **AsianLII / WorldLII / CommonLII** — Cloudflare JS challenge (HTTP 403)
- **Stanford ALEP** — Cloudflare 403 / project page removed
- **moj.gov.af** — scanned gazette PDFs requiring OCR

WIPO Lex is the one source that publishes machine-readable full text and is
reachable without authentication.

## Coverage

21 Afghan legal texts are listed on the WIPO Lex member profile; ~18 have an
extractable text layer (the remainder are scanned image-only originals).
Documents include:

- Constitution of Afghanistan (2004)
- Penal Law for Crimes of Civil Servants (1962)
- Law on Commerce (1955), Customs Law (2005), Press Law (1965)
- Law on Organization and Jurisdiction of Courts (2013)
- Commercial Arbitration & Mediation Laws (2007)
- Competition Law (2010), Private Investment Law (2010)
- Core IP statutes (Copyright 2008, Trademark 2009, Patent 1967)

Texts are in English, Pashto and/or Dari (Farsi). English is preferred where
multiple language versions exist.

## How it works

1. Fetch the server-rendered AF member profile
   (`/wipolex/en/members/profile/AF`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/af/{code}.pdf`.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of Afghanistan (constitution, codes, statutes), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
