# GQ/BoletinOficial — Boletín Oficial del Estado de Guinea Ecuatorial

Official State Gazette of Equatorial Guinea (Boletín Oficial del Estado, BOE).

- **URL**: https://boe.gob.gq/
- **Data type**: legislation
- **Language**: Spanish
- **Coverage**: Laws, decrees, decree-laws, edicts, orders, resolutions, international treaties
- **Documents**: ~146 legal instruments
- **Format**: PDF files with text extraction via pdfplumber

## Strategy

1. POST to `/resultados` with empty search criteria to get all documents
2. Parse HTML result entries (title, date, category, class, summary, PDF URL)
3. Paginate via AJAX endpoint `/masresultados?offset=N` using session cookies
4. Download each PDF and extract full text with pdfplumber

## License

[Open Government Data](https://boe.gob.gq/) — Official government gazette, publicly accessible without authentication. No explicit license terms published; content is official government legislation.
