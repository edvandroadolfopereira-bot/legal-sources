# AO/TribunalConstitucional — Angola Constitutional Court

Decisions (acórdãos) from the Tribunal Constitucional de Angola.

- **Source:** https://www.tribunalconstitucional.ao/pt/jurisprudencia/acordaos/
- **Type:** case_law
- **Records:** 666+ decisions (2008–2026)
- **Language:** Portuguese
- **Format:** HTML full text (Umbraco CMS)

## Coverage

- Extraordinary Appeals of Unconstitutionality (REI)
- Habeas Corpus proceedings
- Abstract/Successive Review of Constitutionality
- Plenary Appeals

## Strategy

1. Paginate listing via POST to `/?altTemplate=jGeneralListingPaging`
2. Extract metadata (decision number, date, formation, rapporteur) from table rows
3. Fetch individual decision pages for full text from `div.umb-grid`

## License

[Public Domain (Government)](https://www.tribunalconstitucional.ao) — Official court decisions are public domain under Angolan law.
