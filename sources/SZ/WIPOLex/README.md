# SZ/WIPOLex — Eswatini Legislation (WIPO Lex)

Full text of the Kingdom of Eswatini's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Eswatini member profile lists the country's industrial-property and
copyright acts and regulations, plus related commercial law: patents, trade
marks, merchandise marks, copyright and neighbouring rights, fair trading and
competition statutes. All texts are in English (Eswatini's legislative
language).

## Why WIPO Lex

Eswatini has no comprehensive open legislation API or bulk download reachable
from outside the country. The consolidated statute collection lives behind the
EswatiniLII platform (a Laws.Africa / LII site whose document pages block
datacenter IPs). WIPO Lex publishes machine-readable Eswatini statute text
without authentication and is a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/SZ`) and parse each legal text's adoption
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
documents are official legislative texts of the Kingdom of Eswatini (acts,
regulations, decrees), which are not subject to copyright. WIPO Lex republishes
them free of charge as a public gateway; no usage restriction is placed on the
underlying legal texts. Commercial use OK.
