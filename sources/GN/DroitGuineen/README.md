# GN/DroitGuineen

**Droitguinéen** — the legal reference portal of the Republic of Guinea.

- **URL**: https://droitguineen.com/
- **Coverage**: 278 legal texts + 156 court decisions
- **Language**: French
- **Data types**: legislation, case_law

## Content

- **Legislation**: Constitution, codes (civil, penal, labor, mining, maritime, etc.), laws, organic laws, ordinances, decrees, OHADA uniform acts
- **Case law**: Supreme Court decisions, Court of Appeal decisions, CCJA (OHADA Common Court of Justice and Arbitration) rulings

## Strategy

1. Parse `sitemap.xml` for all `/lois/` URLs
2. Fetch each page and extract the RSC (React Server Components) JSON payload
3. Extract structured metadata (id, title, nature, date, status) and full text from articles array
4. For jurisprudence, resolve `$XX` RSC references to the full text block

## License

[Terms of Use](https://droitguineen.com/cgu) — Free access. Legal texts are public domain under Guinean law. Attribution to Droitguinéen required.
