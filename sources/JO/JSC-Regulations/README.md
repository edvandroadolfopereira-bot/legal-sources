# JO/JSC-Regulations — Jordan Securities Commission (Regulations & Instructions)

English-language legal corpus published by the **Jordan Securities Commission
(JSC)**, the capital-market regulator:

- **Laws** — the Securities Law and related laws.
- **Regulations** — capital-market regulations (mutual funds, investor
  protection fund, virtual-asset service providers, fees, etc.).
- **Islamic Sukuk Regulating Legislations** — sukuk issuance, trading,
  registration and committee instructions.
- **Instructions** — instructions to issuers and financial-services companies
  (margin finance, corporate governance, disclosure, buyback, etc.).
- **Bases** — supervisory bases and conditions.
- **Regulatory Decisions** — regulator decisions.
- **Related Legislations** — related laws and regulations.

## Source

- Website: https://www.jsc.gov.jo/
- English legislation index: `https://www.jsc.gov.jo/page/en/legislations`
- Category listing pages: `https://www.jsc.gov.jo/Links2/en/{category}`
  (e.g. `/Links2/en/laws`, `/Links2/en/instructions`).
- Each listing is an HTML table whose rows pair a PDF download link
  (`/Uploads/Files/<file>.pdf`) with a description and an issue date/year.

## Method

`bootstrap.py` first visits the homepage to obtain the `lang` session cookie —
without it the site returns an infinite redirect to `/` and PDF downloads return
HTTP 451 (Unavailable For Legal Reasons). It then parses each English category
listing table, downloads each linked PDF through the cookie'd session, and
extracts full text via `common.pdf_extract` (opendataloader-pdf → pdfplumber →
pypdf). Scanned image-only PDFs that yield no text are skipped, and records are
deduplicated by PDF URL. The issue date/year is taken from the table's date
column.

`_type` follows the publisher's grouping: laws, regulations, sukuk legislation
and related legislation are typed `legislation`; instructions, bases and
regulatory decisions are typed `doctrine`.

## License

[Open Government Data — Jordan Securities Commission](https://www.jsc.gov.jo/) —
official securities-regulator laws, regulations, instructions and decisions
published by a Jordanian government authority for public access. No formal
open-license deed is published; treated as open government data (commercial use
permitted for official legal texts).
