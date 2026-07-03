# KI/WIPOLex — Kiribati Legislation (WIPO Lex)

Full text of Kiribati's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for Kiribati

Kiribati is one of the project's data-poor jurisdictions. Every native
legislation channel is blocked or empty:

- **Government Gazette** — only scanned image PDFs (no text layer)
- **Parliament "Acts of Kiribati"** — page 404s
- **Judiciary** — all judgment links redirect to PacLII (paclii.org), which now
  serves a Cloudflare JS challenge to datacenter and residential IPs alike

WIPO Lex is the one source that publishes machine-readable Kiribati statute
text and is reachable without authentication.

## Coverage

21 Kiribati legal texts are listed on the WIPO Lex member profile; most have an
extractable English text layer (a few older originals are scanned image-only).
Documents include:

- Copyright Act 2018
- Registration of UK Patents Ordinance (Cap. 87)
- Registration of UK Trade Marks Ordinance (Cap. 88)
- Registered Designs / Merchandise Marks / Patents ordinances (Gilbert Islands
  Revised Edition 1977)
- Penal Code and related statutes

Texts are in English.

## How it works

1. Fetch the server-rendered KI member profile
   (`/wipolex/en/members/profile/KI`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/ki/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of Kiribati (acts, ordinances, codes), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
