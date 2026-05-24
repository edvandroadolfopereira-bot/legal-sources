# INTL/ESM-Legal — European Stability Mechanism Governance Documents

Governance and policy documents published by the European Stability Mechanism
(ESM) under its transparency framework.

## Coverage

Three transparency sections are scraped:

1. **ESM Policies & Legal Documents** (~35 docs) — ESM Treaty, By-Laws, rules
   of procedure, financial assistance guidelines, MoUs, compliance policies
2. **Programme BoG/BoD Decisions** (~48 docs) — Board of Governors and Board of
   Directors meeting summaries, annotated agendas, staff reports
3. **Board of Auditors Key Documents** (~22 docs) — Annual audit reports and
   management comments

Total: ~105 documents.

## Data Access

Documents are published as PDFs on the ESM website. No API is available.
The scraper:

1. Fetches each transparency section page
2. Parses HTML for PDF download links (Drupal Views)
3. Downloads each PDF from `esm.europa.eu/system/files`
4. Extracts full text using `pdfplumber`

## License

[ESM Terms and Conditions](https://www.esm.europa.eu/terms-and-conditions-and-privacy-statement) — documents published for public transparency; attribution required.
