# NI/SIBOIF-Normativa

**Superintendencia de Bancos y de Otras Instituciones Financieras — Normativa**

Regulatory documents from Nicaragua's banking and financial institutions supervisor (SIBOIF). Covers laws, norms, resolutions, circulars, and regulations for banking, insurance, securities, and warehouse supervision.

- **Source URL:** https://www.superintendencia.gob.ni/consultas/documentos
- **Documents:** ~1125 PDFs
- **Language:** Spanish
- **Data type:** doctrine

## How it works

1. Scrapes the paginated document listing at `/consultas/documentos?page=N`
2. Parses HTML table rows for title, code, type, date, category, and PDF URL
3. Downloads PDFs and extracts text with pdfplumber (fallback to PyMuPDF)
4. Normalizes into standard schema

## License

[Public Domain — Government of Nicaragua](https://www.superintendencia.gob.ni/nosotros/informacion-publica/ley-acceso-informacion-publica) — official regulations published for public access under Nicaragua's Ley de Acceso a la Información Pública (Ley No. 621).
