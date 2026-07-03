# WS/WIPOLex — Samoa Legislation (WIPO Lex)

Full text of the Independent State of Samoa's intellectual-property and
IP-related statutes from the **WIPO Lex** database
(https://www.wipo.int/wipolex/), WIPO's free, open gateway to the laws of ~200
jurisdictions.

## What this covers

The WIPO Lex Samoa member profile lists the country's IP and related law: the
Intellectual Property Act 2011 and Regulations, the Copyright Act 1998, the
trademarks provisions, broadcasting and related commercial acts. Texts are in
English (Samoa's legislative language); a few are also available in Samoan.

## Why WIPO Lex

Samoa's consolidated statutes live behind the SamLII / PacLII platform, which
blocks datacenter IPs on its document pages. WIPO Lex publishes machine-readable
Samoan statute text without authentication and is a stable external full-text
source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/WS`) and parse each legal text's adoption date,
   title and detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL. The
   signed `?last-modified=...` query string is required.
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
documents are official legislative texts of the Independent State of Samoa (acts,
regulations), which are not subject to copyright. WIPO Lex republishes them free
of charge as a public gateway; no usage restriction is placed on the underlying
legal texts. Commercial use OK.
