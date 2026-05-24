# CD/LegalRDC — DRC Court Decisions

Fetches case law from [legalrdc.com](https://legalrdc.com/), a platform providing
free access to court decisions from the Democratic Republic of Congo and the
OHADA Common Court of Justice and Arbitration (CCJA).

## Courts Covered

- **CCJA** — Common Court of Justice and Arbitration (OHADA regional court)
- **Cour de Cassation** — DRC Court of Cassation
- **Conseil d'État** — DRC State Council
- **Cour Constitutionnelle** — DRC Constitutional Court

## Data Access

Uses the WordPress REST API to list posts in jurisprudence categories, then
downloads and extracts text from attached PDF documents using pdfplumber.

~242 decisions available as of May 2026.

## License

> ⚠️ **Commercial use restricted.** No explicit license stated; flagged as non-commercial out of caution.

[legalrdc.com Terms](https://legalrdc.com/) — Court decisions are published freely but no open data license is declared. Attribution recommended.
