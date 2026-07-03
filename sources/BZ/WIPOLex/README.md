# BZ/WIPOLex — Belize Legislation (WIPO Lex)

Full text of Belize's legislation, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database (WIPO's free, open gateway to
the laws of ~200 jurisdictions).

## What it collects

The [Belize member profile](https://www.wipo.int/wipolex/en/members/profile/BZ)
lists ~49 legal texts — including the Constitution of Belize, the Trade Marks
Act, the Patents Act, the Copyright Act, industrial designs, layout-designs of
integrated circuits, plant breeders' rights, the Income and Business Tax Act,
competition and consumer protection statutes, their subsidiary regulations and
related commercial legislation. Each detail page exposes a CloudFront-signed PDF
download; the scraper downloads it and extracts the full text (English, Belize's
legislative language).

This complements the global **INTL/WIPOLex** source, which captures only the
documents that expose inline HTML full text and explicitly skips PDF-only laws —
the bulk of Belize's corpus.

## How it works

1. Fetch the server-rendered member profile HTML and parse each row's adoption
   date, title, and `/wipolex/en/legislation/details/{id}` link.
2. For each detail page, extract the signed
   `https://wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/bz/{code}.pdf` URL
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

[Public domain (national legislation)](https://www.wipo.int/wipolex/en/disclaimer) — the underlying documents are official legislative texts of Belize, which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the legal texts. Commercial use permitted.
