# SD/WIPOLex — Sudan Legislation (WIPO Lex)

Full text of the Republic of the Sudan's intellectual-property and IP-related
statutes from the **WIPO Lex** database (https://www.wipo.int/wipolex/), WIPO's
free, open gateway to the laws of ~200 jurisdictions.

## What this covers

The WIPO Lex Sudan member profile lists the country's industrial-property and
copyright acts and regulations — patents, trade marks, industrial designs,
copyright and neighbouring rights — together with broader commercial
instruments such as the Investment Encouragement Act and the Customs Act. Texts
are published in English and Arabic; English is preferred when available.

## Why WIPO Lex

Sudan has no comprehensive open legislation API or bulk download reachable from
outside the country, and the public gazette / national assembly portals are
unreliable from datacenter IPs and largely serve scanned PDFs. WIPO Lex
publishes machine-readable Sudan statute text without authentication and is
reachable from datacenter IPs, making it a stable external full-text source.

## How it works

1. Fetch the server-rendered member profile
   (`/wipolex/en/members/profile/SD`) and parse each legal text's adoption
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
documents are official legislative texts of the Republic of the Sudan (acts,
regulations, decrees), which are not subject to copyright. WIPO Lex republishes
them free of charge as a public gateway; no usage restriction is placed on the
underlying legal texts. Commercial use OK.
