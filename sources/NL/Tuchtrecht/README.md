# NL/Tuchtrecht — Dutch Professional Disciplinary Tribunals

Full-text disciplinary case law from **tuchtrecht.overheid.nl**, the official
Dutch government collection of professional disciplinary decisions
(tuchtrechtspraak). It complements [`NL/Rechtspraak`](../Rechtspraak/) (the
ordinary courts) by covering the disciplinary tribunals for the regulated
professions.

## Coverage

~47,600 ECLI-indexed decisions (2010–present) across the disciplinary
tribunals and their appellate bodies:

| Profession (domein)        | Tribunals |
|----------------------------|-----------|
| Advocaten (lawyers)        | Raden van Discipline · Hof van Discipline |
| Gezondheidszorg (health)   | Regionale Tuchtcolleges · Centraal Tuchtcollege voor de Gezondheidszorg |
| Notarissen                 | Kamers voor het notariaat · Hof Amsterdam |
| Gerechtsdeurwaarders       | Kamer voor gerechtsdeurwaarders |
| Accountants                | Accountantskamer · College van Beroep voor het bedrijfsleven |
| Diergeneeskundigen (vets)  | Veterinair Tuchtcollege · Veterinair Beroepscollege |
| Scheepvaart (maritime)     | Tuchtcollege voor de Scheepvaart |

## Data access

KOOP **SRU 2.0** open-data API — no authentication.

- **Index/search:** `https://repository.overheid.nl/sru?operation=searchRetrieve&version=2.0&query=c.product-area==tuchtrecht&maximumRecords=100&startRecord=N`
  - Linear `startRecord` pagination works to the end of the collection (no deep-pagination cap).
  - Each record exposes `dcterms` metadata + a direct XML manifestation URL.
- **Full text:** the per-decision XML (`manifestation="xml"` itemUrl), e.g.
  `https://repository.overheid.nl/frbr/tuchtrecht/2016/ECLI:NL:TADRARL:2016:108/1/xml/ECLI_NL_TADRARL_2016_108.xml`
  - Full reasoning body in `<uitspraaktekst>`; headnote in `<inhoudsindicatie>`.

## Usage

```bash
python bootstrap.py test-api                  # connectivity + full-text check
python bootstrap.py bootstrap --sample        # 12 validation samples
python bootstrap.py bootstrap                  # full pull (~47.6K decisions)
python bootstrap.py update                     # incremental (modified since last run)
```

## Output schema

Each normalized record contains `_id` (ECLI), `_source` (`NL/Tuchtrecht`),
`_type` (`case_law`), `title`, **`text`** (full decision body), `date`
(ISO 8601 `uitspraakdatum`), `url`, plus `court`, `domain`, `case_numbers`,
`subjects`, `decisions`, `arrondissement`, and `modified`.

## License

[Public Domain — Dutch official documents (Art. 11 Auteurswet)](https://www.overheid.nl/help/algemeen/copyright) — no attribution required.

Under Article 11 of the Dutch Copyright Act (Auteurswet), there is no copyright
on judicial decisions and laws issued by or on behalf of a public authority.
Decisions published on tuchtrecht.overheid.nl are official government documents
in the public domain. Personal data is pseudonymized by the publisher before
publication. Commercial use is permitted.
