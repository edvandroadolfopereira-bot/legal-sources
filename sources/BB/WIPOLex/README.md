# BB/WIPOLex — Barbados Legislation (WIPO Lex)

Full text of Barbados's legislation, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database (WIPO's free, open gateway to
the laws of ~200 jurisdictions).

## What it collects

The [Barbados member profile](https://www.wipo.int/wipolex/en/members/profile/BB)
lists ~45 legal texts — including the Constitution of Barbados, the Trade Marks
Act, the Patents Act, the Copyright Act, the Industrial Designs Act, integrated
circuit topographies, geographical indications, the Protection Against Unfair
Competition Act, the Telecommunications Act and related commercial and
fair-competition legislation, with their subsidiary regulations and orders. Each
detail page exposes a CloudFront-signed PDF
download; the scraper downloads it and extracts the full text (English, Barbados's
legislative language).

This complements the global **INTL/WIPOLex** source, which captures only the
documents that expose inline HTML full text and explicitly skips PDF-only laws —
the bulk of Barbados's corpus.

## How it works

1. Fetch the server-rendered member profile HTML and parse each row's adoption
   date, title, and `/wipolex/en/legislation/details/{id}` link.
2. For each detail page, extract the signed
   `https://wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/bb/{code}.pdf` URL
   (the `?last-modified=...` query string is required).
3. Download and extract full text via the shared `common.pdf_extract` backend.
   Scanned image-only PDFs with no text layer are skipped.

## Usage

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain (national legislation)](https://www.wipo.int/wipolex/en/disclaimer) — the underlying documents are official legislative texts of Barbados, which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the legal texts. Commercial use permitted.
