# MR/WIPOLex — Mauritania Legislation (WIPO Lex)

Full text of the Islamic Republic of Mauritania's statutes from the **WIPO Lex**
database (https://www.wipo.int/wipolex/), WIPO's free, open gateway to the laws
of ~200 jurisdictions.

## What this covers

The WIPO Lex Mauritania member profile lists the country's industrial-property
and copyright acts and regulations together with broader instruments — the
Commercial Code, the Public Procurement Code, the Telecommunications Law, and
higher-education and environment framework laws. Texts are published in French
and Arabic; French is preferred when available, then Arabic.

## Why WIPO Lex

Mauritania has no comprehensive open legislation API or bulk download reachable
from outside the country, and the official gazette / government portals are
unreliable from datacenter IPs and largely serve scanned PDFs. WIPO Lex
publishes machine-readable Mauritania statute text without authentication and is
reachable from datacenter IPs, making it a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/MR`) and parse each legal text's adoption
   date, title and detail-page link.
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
documents are official legislative texts of the Islamic Republic of Mauritania
(laws, codes, ordinances, decrees), which are not subject to copyright. WIPO Lex
republishes them free of charge as a public gateway; no usage restriction is
placed on the underlying legal texts. Commercial use OK.
