# BG/CPC — Bulgarian Commission for Protection of Competition

Public electronic registry of the Commission for Protection of Competition
(Комисия за защита на конкуренцията / КЗК).

**URL:** https://reg.cpc.bg/
**Data types:** case_law (decisions, determinations, orders)
**Coverage:** 2008–present
**Legal frameworks:**
- Competition Protection Act (ЗЗК)
- Public Procurement Act (ЗОП)
- Concessions Act (ЗК)

## Method

ASP.NET WebForms HTML scraping with PDF text extraction:
1. Navigate `AllResolutions.aspx` listing pages (years + pagination via `__doPostBack`)
2. Extract dossier IDs and metadata from listing tables
3. Fetch individual `Dossier.aspx?DossID=` pages
4. Download decision PDFs via ASP.NET postback
5. Extract full text from PDFs using pdfplumber

## License

[Public Domain (Government)](https://reg.cpc.bg/) — official public register of a Bulgarian government authority. Bulgarian government documents are in the public domain per Bulgarian copyright law.
