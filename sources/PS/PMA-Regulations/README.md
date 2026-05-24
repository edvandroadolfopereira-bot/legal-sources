# PS/PMA-Regulations

**Palestine Monetary Authority — Regulations**

Regulatory documents from Palestine's monetary authority (PMA). Covers laws, circulars, instructions, and regulations for banking and financial supervision.

- **Source URL:** https://www.pma.ps/
- **Documents:** ~2054
- **Language:** Arabic (primary)
- **Data type:** doctrine

## How it works

1. Queries the Supabase REST API at `fayupjvyvxedvgathafk.supabase.co/rest/v1/documents`
2. Filters for regulatory categories (laws, circulars, instructions, regulations)
3. Downloads PDFs from Supabase storage and extracts text with pdfplumber/PyMuPDF
4. Normalizes into standard schema

## License

Public Domain — official Palestinian Authority regulations published for public access under Palestinian transparency legislation.
