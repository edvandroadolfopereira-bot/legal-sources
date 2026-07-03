# BW/WIPOLex — Botswana Legislation (WIPO Lex)

Full-text Botswana statutes harvested from the **WIPO Lex** database
(<https://www.wipo.int/wipolex/>), WIPO's free, open gateway to the
intellectual-property and IP-related laws of ~200 jurisdictions.

For Botswana, WIPO Lex publishes the full text of core statutes — the
Constitution, the Industrial Property Act, the Copyright and Neighbouring
Rights Act, the Companies Act, the Trade Marks Act and a range of related acts
— as machine-readable English PDF documents.

## Why WIPO Lex

Botswana's native legislation channels are all blocked or dead:

- **BotswanaLII** (botswanalii.org) — DNS no longer resolves
- **elaws.gov.bw** — DNS failure
- **BotswanaLaws** (Blackhall Publishing) — private commercial paywall

WIPO Lex is the one source publishing machine-readable Botswana statute text
reachable without authentication and from datacenter IPs.

## How it works

1. Fetch the WIPO Lex Botswana member profile
   (`/wipolex/en/members/profile/BW`) — server-rendered HTML listing each legal
   text with its adoption date and a detail-page link.
2. For each detail page, extract the CloudFront-signed PDF download URL
   (`https://wipolex-res.wipo.int/edocs/lexdocs/laws/en/bw/{code}.pdf`). The
   signed `?last-modified=...` query string is required.
3. Download each PDF and extract full text via the shared `pdf_extract` backend
   (pdfplumber / pypdf / fitz). A few older originals are scanned image-only
   PDFs with no text layer and are skipped.

## Usage

```bash
python bootstrap.py test                # verify profile + detail + PDF access
python bootstrap.py bootstrap --sample  # fetch a sample set
python bootstrap.py bootstrap --full    # fetch the full BW corpus
```

## License

[Public domain — national legislation](https://www.wipo.int/wipolex/en/disclaimer) — no attribution required.

The documents are official legislative texts of Botswana (acts, statutory
instruments, codes), which are not subject to copyright. WIPO Lex republishes
them free of charge as a public gateway; no usage restriction is placed on the
underlying legal texts.
