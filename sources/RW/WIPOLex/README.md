# RW/WIPOLex — Rwanda Legislation (WIPO Lex)

Full text of the Republic of Rwanda's legislation, sourced from the
[WIPO Lex](https://www.wipo.int/wipolex/) database (WIPO's free, open gateway to
the laws of ~200 jurisdictions).

## What it collects

The [Rwanda member profile](https://www.wipo.int/wipolex/en/members/profile/RW)
lists ~29 legal texts — intellectual-property statutes (copyright and related
rights, patents, trademarks, industrial designs, plant breeders' rights) and
related commercial legislation, competition and consumer protection, their
implementing orders and subsidiary regulations. Each detail page exposes a
CloudFront-signed PDF download; the scraper downloads it and extracts the full
text (English preferred, French fallback — Rwanda is officially trilingual:
Kinyarwanda, English and French).

This complements the global **INTL/WIPOLex** source, which captures only the
documents that expose inline HTML full text and explicitly skips PDF-only laws —
the bulk of Rwanda's corpus.

## How it works

1. Fetch the server-rendered member profile HTML and parse each row's adoption
   date, title, and `/wipolex/en/legislation/details/{id}` link.
2. For each detail page, extract the signed
   `https://wipolex-res.wipo.int/edocs/lexdocs/laws/{lang}/rw/{code}.pdf` URL
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

[Public domain (national legislation)](https://www.wipo.int/wipolex/en/disclaimer) — the underlying documents are official legislative texts of the Republic of Rwanda, which are not subject to copyright. WIPO Lex republishes them free of charge as a public gateway; no usage restriction is placed on the legal texts. Commercial use permitted.
