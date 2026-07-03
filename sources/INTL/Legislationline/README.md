# INTL/Legislationline

OSCE/ODIHR Legal Opinions & Comments (formerly Legislationline).

Expert legal reviews of draft and enacted laws across OSCE participating states —
elections, political party financing, the judiciary, anti-discrimination, freedom of
assembly, and related rule-of-law topics. Each document has an introductory summary
plus a full-text PDF opinion. ~220 documents, all with full text.

**History:** The legacy `legislationline.org` Drupal JSON:API was decommissioned in
2026; the domain now 302-redirects to `odihr.osce.org/odihr/legal-opinions-and-comments`
(Drupal 11, no JSON:API). The old ~14K national-legislation corpus (constitutions,
criminal codes) was not carried over to the new site. See issue #973.

**Method:** HTML listing scrape (`/odihr/legal-opinions-and-comments`) + per-node
PDF full-text extraction via `common.pdf_extract`.

Documents are advisory legal opinions/commentary, classified as `doctrine`.

## Usage

```bash
python bootstrap.py test                  # Test connectivity + PDF extraction
python bootstrap.py bootstrap --sample    # Fetch 12 sample records
python bootstrap.py bootstrap --full      # Full bootstrap -> data/records.jsonl
python bootstrap.py bootstrap-fast        # VPS pipeline alias
```

## License

[OSCE Copyright & Reproduction](https://www.osce.org/copyright) — OSCE/ODIHR content is freely reproducible with attribution to OSCE/ODIHR; no explicit commercial-use restriction.
