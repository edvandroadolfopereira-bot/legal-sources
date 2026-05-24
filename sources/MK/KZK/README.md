# MK/KZK — North Macedonia Commission for Protection of Competition

Decisions of the Commission for Protection of Competition (Комисија за
заштита на конкуренцијата, KZK). Covers competition law (mergers,
prohibited agreements, abuse of dominance), state aid, and unfair
commercial practices decisions.

- **URL**: https://kzk.gov.mk/
- **Language**: Macedonian
- **Format**: PDF decisions embedded in Joomla CMS pages
- **Coverage**: Administrative procedure decisions, violation proceedings,
  court decisions, state aid acts/opinions, unfair commercial practices

## Strategy

1. Scrape paginated Joomla blog listings for each decision category
2. Extract metadata (title, date, PDF URL) from article HTML
3. Download each PDF and extract full text via pdfplumber
4. Normalize into standard schema

## License

[Public Domain](https://kzk.gov.mk/) — Official government competition authority decisions published in the public interest. North Macedonia government decisions are public domain.
