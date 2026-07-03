# TV/WIPOLex — Tuvalu Legislation (WIPO Lex)

Full text of Tuvalu's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for Tuvalu

Tuvalu is one of the project's data-poor jurisdictions. Its native legislation
channels are blocked or empty:

- **tuvalu-legislation.tv** — the dedicated official legislation site serves
  only a 294-byte blank shell (no titles, no documents)
- **PacLII** (paclii.org) — the historical Pacific legislation gateway now
  returns HTTP 410 Gone behind a Cloudflare/ALTCHA anti-bot challenge to
  datacenter and residential IPs alike

WIPO Lex is the one source that publishes machine-readable Tuvalu statute text
and is reachable without authentication.

## Coverage

23 Tuvalu legal texts are listed on the WIPO Lex member profile; most have an
extractable English text layer (a few older originals are scanned image-only).
Documents include:

- Copyright Act (Chapter 40.24, Revised Edition 2008)
- United Kingdom Trade Marks (Registration) Ordinance
- United Kingdom Patents (Registration) Ordinance
- United Kingdom Designs (Protection) Ordinance
- Merchandise Marks Act and related statutes

Texts are in English.

## How it works

1. Fetch the server-rendered TV member profile
   (`/wipolex/en/members/profile/TV`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/tv/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of Tuvalu (acts, ordinances, codes), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
