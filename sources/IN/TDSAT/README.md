# IN/TDSAT — Telecom Disputes Settlement and Appellate Tribunal

Final judgments from India's TDSAT, a specialized tribunal handling telecom, broadcasting, airport economic regulation (AERA), and cyber disputes.

## Coverage

- **Case types**: Telecom appeals/petitions, broadcasting disputes, AERA appeals, cyber appeals, misc applications, review applications
- **Period**: 2001–present
- **Format**: PDF (text-based, extractable via pdfplumber)
- **Volume**: ~1,500 final judgments

## Data Access

Uses the TDSAT judgment search at `https://tdsat.gov.in/Delhi/services/judgment.php`:
1. POST date-wise search parameters to get listing of all judgments
2. Parse HTML table for case metadata and PDF download links
3. Download PDFs and extract text via pdfplumber

## License

[Indian Government Public Court Records](https://tdsat.gov.in/) — Public tribunal judgments. No restrictions on access.
