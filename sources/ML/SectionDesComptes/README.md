# ML/SectionDesComptes — Cour Suprême du Mali

Court decisions (arrêts) from Mali's Supreme Court across all chambers.

## Data types

- **case_law**: Court decisions from Civile, Criminelle, Commerciale,
  Sociale, and Administrative chambers
- **doctrine**: News posts and judicial announcements

## Strategy

WordPress REST API at `wp-json/wp/v2`:
- 6 pages contain PDF links to court decisions (~121 PDFs)
- PDFs downloaded and text extracted via pdfplumber
- 22 news posts with inline HTML text
- Dates parsed from PDF filenames (e.g., "du-14-juillet-2023")

## License

[Public Government Documents (Mali)](https://www.coursupreme.ml/) — official
court decisions. Attribution required.
