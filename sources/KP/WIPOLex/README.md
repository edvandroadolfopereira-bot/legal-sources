# KP/WIPOLex — North Korea (DPRK) Legislation (WIPO Lex)

Full text of North Korea's core statutes, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database — WIPO's free, open gateway
to the IP and IP-related laws of ~200 jurisdictions.

## Why WIPO Lex for North Korea

North Korea is one of the world's most closed jurisdictions. There is no public
government legislation portal reachable from outside the country. WIPO Lex is
effectively the only source that publishes machine-readable DPRK statute text
without authentication — which is why it is the project's first KP source.

## Coverage

25 DPRK legal texts are listed on the WIPO Lex member profile, with extractable
English and/or Korean text layers. Documents include:

- Intellectual Property Law of the DPRK
- Law on Inventions
- Law on Industrial Designs
- Law on Trademarks
- Law on Copyright
- and related IP/IP-adjacent statutes

Texts are in English where available, Korean otherwise.

## How it works

1. Fetch the server-rendered KP member profile
   (`/wipolex/en/members/profile/KP`) and parse each table row for adoption
   date, title and the legislation detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL(s) from
   `wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/kp/{code}.pdf`. The signed
   `?last-modified=...` query string is required — the bare URL returns an HTML
   error page. English is preferred, Korean used as fallback.
3. Download the PDF and extract full text via the shared `pdf_extract` backend.

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — the documents are official legislative texts of the Democratic People's Republic of Korea (laws, regulations), which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the underlying legal texts.
