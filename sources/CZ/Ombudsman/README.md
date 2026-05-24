# CZ/Ombudsman — Czech Ombudsman ESO Database

Evidence stanovisek ombudsmana (ESO) — the database of findings and positions
of the Czech Public Defender of Rights (Veřejný ochránce práv).

- **URL**: https://eso.ochrance.cz
- **Coverage**: 2000–present
- **Documents**: ~6,500+ investigation reports, legal opinions, discrimination findings
- **Language**: Czech
- **Data type**: doctrine
- **Full text**: Yes — HTML detail pages contain complete document text

## Access Method

Session-based web scraping:
1. POST search form to `/Vyhledavani/Search` to select all documents
2. Paginate through `/Nalezene/GetTableContent` AJAX endpoint (50 rows/page)
3. Fetch individual detail pages at `/Nalezene/Edit/{id}` for full text

## License

[Open Government Data (Czech Republic)](https://data.gov.cz) — published on official
government website as public transparency data under Czech open data regulations.
