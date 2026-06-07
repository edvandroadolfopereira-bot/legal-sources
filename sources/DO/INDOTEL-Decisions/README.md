# DO/INDOTEL-Decisions — INDOTEL Board of Directors Resolutions

Full-text resolutions of the Board of Directors (Consejo Directivo) of the
**Instituto Dominicano de las Telecomunicaciones (INDOTEL)**, the Dominican
Republic's telecommunications regulator. These are the binding regulatory and
adjudicatory acts INDOTEL issues under the General Telecommunications Law (Ley
General de Telecomunicaciones, núm. 153-98): spectrum and frequency assignments,
broadcasting and operator concessions/licences, sanctioning procedures, public
consultations, interconnection, numbering, tariffs, universal service, and
reconsideration appeals.

Classified as `doctrine` (regulatory acts of a public institution).

## Data access

- **Method:** single HTML listing page + PDF full-text extraction (`pdfplumber`).
- **Listing:** `/transparencia/documentos/resoluciones-del-consejo-directivo/`
  enumerates the entire corpus (~3,300 resolutions) as static HTML.
- Each entry is a `<li class="el-archivo-N">` block carrying a
  `<span class="name">` (e.g. "Resolución No. 032-2026"), a direct link to a
  `/wp-content/uploads/YYYY/MM/*.pdf` file, a descriptive subject, file size, and
  an upload date ("Fecha de subida").
- The resolution's own date is recovered from the body's page-footer formula
  (`...del INDOTEL de fecha DD de MES de YYYY`), falling back to the listing
  upload date.
- A **browser User-Agent is required** — the server returns HTTP 473 to
  non-browser agents. TLS verification is disabled (public, read-only data).
- Rate limit: 1 request/second.

## Record fields

`_id`, `_source`, `_type` (`doctrine`), `_fetched_at`, `title` (resolution number
+ subject), `text` (full PDF body), `date`, `url`, `summary`, `doc_number` (e.g.
`032-2026`), `issuer`, `jurisdiction`, `language`, `pdf_size`.

## License

[Open Government Data — Dominican Republic](https://indotel.gob.do/) — official
regulatory resolutions published by a Dominican public institution (INDOTEL) on
its transparency portal for public use. Attribution to INDOTEL appreciated.
Commercial use permitted (public official regulatory texts).
