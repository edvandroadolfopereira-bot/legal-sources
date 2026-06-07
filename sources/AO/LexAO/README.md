# AO/LexAO

Lex.ao — Free Angolan Legal Platform. Full text of Angolan legislation from the National Assembly, People's Assembly, and regulatory agencies.

## Coverage

- **Institutions:** Assembleia Nacional, Assembleia do Povo, AARSEG (Insurance Regulator), ANPG (Oil & Gas Agency)
- **Document types:** Laws (Leis), Presidential Decrees, Executive Decrees, Resolutions, Regulatory Standards, Directives
- **Period:** 1982–present
- **Volume:** 1,200+ legal diplomas
- **Language:** Portuguese

## Data access

Docusaurus static site. Documents enumerated via `sitemap.xml`, full text extracted from HTML pages.

```
GET https://lex.ao/sitemap.xml
GET https://lex.ao/docs/{institution}/{year}/{document-slug}/
```

## License

[Lex.ao](https://lex.ao/) — free public access to Angolan legislation. No formal open data license published.
