# INTL/ACHPR-Communications

African Commission on Human and Peoples' Rights — Decisions on Communications.

Quasi-judicial decisions on individual and inter-state complaints ("communications")
filed under the African Charter on Human and Peoples' Rights (Banjul Charter).
Covers merits, admissibility, and inadmissibility decisions from 1994 to present.

Distinct from the African Court on Human and Peoples' Rights (see `INTL/AfCHPR`).

## Data

- **Type:** case_law
- **Source:** https://achpr.au.int/en/category/decisions-communications
- **Records:** ~300 communications with full decision text
- **Avg text length:** ~80K characters per decision

## Strategy

1. Paginate the listing at `achpr.au.int/en/category/decisions-communications?page=N`
2. For each communication, fetch the detail page to extract metadata and PDF links
3. Download decision PDFs (English preferred; transmittal letters excluded)
4. Extract full text from PDFs via `common/pdf_extract.py`

## License

[African Union Open Data](https://au.int/en/legal-instruments) — decisions of a treaty body of the African Union, published as public records. No explicit license deed; treated as open government data.
