# CV/TribunalConstitucional — Cabo Verde Constitutional Court Decisions

Fetches decisions of the **Tribunal Constitucional da República de Cabo Verde**,
the highest court in the Cape Verdean judicial system for constitutional matters.

- **Source:** https://www.tribunalconstitucional.cv/
- **Data type:** `case_law`
- **Language:** Portuguese (pt)
- **Coverage:** Acórdãos (judgments) and Pareceres (advisory opinions on
  preventive constitutionality review), from the "últimas decisões" page and
  per-year archives (2017–present).

## How it works

Decisions are published as direct PDF downloads on the court's Joomla site
(`/index.php/download/.../<file>.pdf`), linked from the latest-decisions page and
each yearly archive page. The scraper collects those links, downloads each PDF,
and extracts the full text with `pypdf`. The decision date is parsed from the
signature line in the body ("Praia, aos N de mês de ano"), preferring the date
whose year matches the document's archive year; the case number, document type
(acórdão / parecer / decisão sumária) and year are parsed from the title.

Each record contains the complete decision text in the `text` field.

## Run

```bash
python3 bootstrap.py bootstrap --sample   # 15 recent decisions
python3 bootstrap.py bootstrap --full     # all decisions
```

## License

[Public Domain](https://creativecommons.org/publicdomain/mark/1.0/) — official
judicial decisions of the Republic of Cabo Verde. Government works (laws and
court decisions) are not subject to copyright; free to use including commercially.
