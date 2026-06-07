# JM/OUR-Decisions — Office of Utilities Regulation (Jamaica)

Determination notices, decisions, regulations, and directives issued by the
**Office of Utilities Regulation (OUR)**, Jamaica's independent multi-sector
economic regulator. The OUR regulates electricity, telecommunications, water &
sewerage, and public passenger transport, setting tariffs and quality-of-service
standards for licensees such as the Jamaica Public Service Company (JPS) and the
National Water Commission (NWC).

## Data

- **Type:** doctrine (binding regulatory determinations)
- **Coverage:** ~550 documents across four categories — Determination Notices
  (311), Decisions and Regulations (169), Decisions & Regulations (32), and
  Directives (42). Spanning 2001–present.
- **Language:** English

## Method

1. Enumerate documents via the WordPress REST API custom `document` post type,
   filtered to the regulatory-output categories
   (`/wp-json/wp/v2/document?categories=...`).
2. Fetch each document's page and extract the linked PDF under
   `/wp-content/uploads/`.
3. Download the PDF and extract full text (opendataloader-pdf → pdfplumber →
   pypdf).
4. Skip records whose PDFs are scanned image-only (no text layer) — some older
   notices have no extractable text.

```bash
python bootstrap.py test-api            # category document counts
python bootstrap.py bootstrap --sample  # 15 sample records
python bootstrap.py bootstrap           # full pull
```

## License

[Open Government Data (Jamaica)](https://our.org.jm/) — official regulator
determinations published for public access on the OUR Jamaica government-agency
website. Commercial use permitted; no formal license deed is published, so the
content is treated as open government data.
