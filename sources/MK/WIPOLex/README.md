# MK/WIPOLex — North Macedonia Legislation (WIPO Lex)

Full-text North Macedonia statutes harvested from the **WIPO Lex** database
(<https://www.wipo.int/wipolex/>), WIPO's free, open gateway to the
intellectual-property and IP-related laws of ~200 jurisdictions.

For North Macedonia, WIPO Lex publishes the full text of core statutes — the
Constitution, the Penal Code, the Code of Criminal Procedure, the Customs Code,
the Law on Copyright and Related Rights, the Law on Industrial Property and a
range of related acts — as machine-readable PDF documents, in both English
(WIPO translations) and Macedonian.

## Why WIPO Lex

North Macedonia's native legislation channels are blocked from outside the
country:

- **Sluzben Vesnik** (slvesnik.com.mk) — Official Gazette portal, blocked
- **Sobranie** (sobranie.mk) — Assembly law database, blocked

WIPO Lex is a stable source publishing machine-readable North Macedonia statute
text reachable without authentication and from datacenter IPs.

## How it works

1. Fetch the WIPO Lex North Macedonia member profile
   (`/wipolex/en/members/profile/MK`) — server-rendered HTML listing each legal
   text with its adoption date and a detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL
   (`https://wipolex-res.wipo.int/edocs/lexdocs/laws/en/mk/{code}.pdf`). The
   signed `?last-modified=...` query string is required. English is preferred,
   Macedonian as fallback.
3. Download each PDF and extract full text via the shared `pdf_extract` backend
   (pdfplumber / pypdf / fitz). A few older originals are scanned image-only
   PDFs with no text layer and are skipped.

## Usage

```bash
python bootstrap.py test                # verify profile + detail + PDF access
python bootstrap.py bootstrap --sample  # fetch a sample set
python bootstrap.py bootstrap --full    # fetch the full MK corpus
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — no attribution required.

The documents are official legislative texts of North Macedonia (the
Constitution, codes and acts), which are not subject to copyright. WIPO Lex
republishes them free of charge as a public gateway; no usage restriction is
placed on the underlying legal texts.
