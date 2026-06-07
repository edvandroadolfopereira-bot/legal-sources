# HR/AZTN — Croatian Competition Agency (AZTN)

Agencija za zaštitu tržišnog natjecanja (AZTN) — decisions on competition law
and unfair trading practices in Croatia.

## Data

- **Type:** case_law (competition decisions, merger assessments, unfair trading practices)
- **Coverage:** 2003–present
- **Volume:** ~1,800 agency decisions + ~220 court decisions
- **Language:** Croatian (HR)
- **Access:** Custom WordPress REST API (`wp/ea/decision`) + PDF downloads
- **Auth:** None

## Strategy

1. Query the custom WP REST API year-by-year (2003–current)
2. Two post type groups: agency decisions (`state_decision` + `decision`) and court decisions (`court_decision`)
3. Download PDFs from `document_file_hr` field
4. Extract full text using pdfplumber

## License

[Public authority decisions](https://www.aztn.hr/) — official decisions published by a Croatian government agency for public access. No explicit license; content is public administrative law.
