# INTL/FAOLEX — FAO Legislation Database (FAOLEX)

**Source:** [https://www.fao.org/faolex/en/](https://www.fao.org/faolex/en/)
**Data types:** legislation

FAOLEX is one of the world's largest online repositories of national laws, regulations,
and policies on food, agriculture, natural resources, and environment. Contains 220K+
records from 200+ countries with full text available via pre-extracted .txt files.

## Method

1. Download bulk CSV from [FAOLEX Open Data](https://www.fao.org/faolex/opendata/en/)
2. Parse metadata (record ID, title, date, country, keywords, abstract)
3. Fetch full text from per-record `.txt` URLs on `faolex.fao.org`

## License

> ⚠️ **Commercial use restricted.** Non-commercial only under share-alike terms.

[CC BY-NC-SA 3.0 IGO](https://creativecommons.org/licenses/by-nc-sa/3.0/igo/) — Attribution, non-commercial, share-alike required.
