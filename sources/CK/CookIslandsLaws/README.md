# CK/CookIslandsLaws — Cook Islands Consolidated Legislation Portal

Official consolidated legislation portal for the Cook Islands at
[cookislandslaws.gov.ck](https://cookislandslaws.gov.ck/).

## Data

- **Type**: Legislation (consolidated acts)
- **Volume**: ~271 acts
- **Format**: REST API returning JSON (act listings/TOC) and HTML (section content)
- **Language**: English, some Maori

## Approach

1. List all acts via `/api/retrieve_all_act`
2. For each act, fetch table of contents via `/api/retrieve_toc/{ActName}`
3. Extract section IDs from nested TOC structure
4. Fetch each section's HTML content via `/api/display_pages/{section_id}`
5. Strip HTML tags and concatenate sections for full text

## License

[Public Domain](https://en.wikipedia.org/wiki/Public_domain) — government legislation is public law and not subject to copyright in the Cook Islands.
