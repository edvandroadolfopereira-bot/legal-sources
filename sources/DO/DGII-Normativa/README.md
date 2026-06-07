# DO/DGII-Normativa — Dirección General de Impuestos Internos (Normas Generales & Resoluciones)

Regulatory output of the Dominican Republic tax authority (Dirección General de
Impuestos Internos, DGII). Covers the **Normas Generales** — binding general
norms the DGII issues under articles 34–35 of the Tax Code (Ley 11-92) on income
tax (ISR), VAT (ITBIS), selective consumption tax (ISC), fiscal vouchers
(comprobantes fiscales), incentive laws, casinos and games of chance, motor
vehicles, asset tax, and sectoral matters — plus the DGII's **Resoluciones**.

These are administrative normative acts of a public institution, so they are
classified as `doctrine` (the Tax Code and laws themselves belong to legislation
sources).

## Data access

- **Method:** HTML listing pages + PDF full-text extraction (`pdfplumber`).
- **Listings:**
  - `/legislacion/normasGenerales/Paginas/default.aspx` (~176 norms)
  - `/legislacion/resoluciones/Paginas/default.aspx` (~61 resolutions)
- Each listing anchor carries a descriptive title plus `Año:` / `Modificado:`
  metadata and links directly to a `/Documents/*.pdf` file.
- ~237 unique documents discovered. PDFs are downloaded and text-extracted.
- TLS verification is disabled (the server presents an incomplete certificate
  chain); data is public and read-only.
- Rate limit: 1 request/second.

## Record fields

`_id`, `_source`, `_type` (`doctrine`), `_fetched_at`, `title`, `text` (full PDF
body), `date`, `url`, `category` (`norma_general` | `resolucion`), `subcategory`
(topical folder), `doc_number`, `year`, `issuer`, `jurisdiction`, `language`,
`pdf_size`.

## License

[Open Government Data — Dominican Republic](https://dgii.gov.do/) — official tax
norms and resolutions published by a Dominican public institution (DGII) for
public use. Attribution to DGII appreciated. Commercial use permitted (public
official legal/administrative texts).
