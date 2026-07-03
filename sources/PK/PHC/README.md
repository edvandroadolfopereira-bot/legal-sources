# PK/PHC — Peshawar High Court (Reported Judgments)

Reported judgments of the **Peshawar High Court**, the constitutional High Court
for **Khyber Pakhtunkhwa** province, Pakistan. Data is served from the court's
official **Case Flow Management System (PHCCMS)**.

- **Portal:** https://www.peshawarhighcourt.gov.pk/PHCCMS/reportedJudgments.php
- **Type:** case_law
- **Coverage:** 2010–present (Criminal, Civil, Revenue, Constitutional, Service, Corporate)
- **Language:** English
- **Auth:** none

## How it works

The reported-judgments page is a POST search form
(`/PHCCMS/reportedJudgments.php?action=search`) accepting `year`, `category` and
`judge` filters. `bootstrap.py` issues one POST per year, parses the result
table (case title, headnote/principle, decision date, category) and follows each
row's link to a full-text judgment PDF under `/PHCCMS/judgments/<file>.pdf`. PDF
text is extracted with `pdfplumber`. Image-only/scanned PDFs (no extractable
text layer) are skipped.

### Usage

```bash
python bootstrap.py bootstrap --sample     # ~12 sample records
python bootstrap.py bootstrap              # all judgments -> data/records.jsonl
python bootstrap.py updates --since 2024-01-01
```

## Normalized record

`_id`, `_source` (`PK/PHC`), `_type` (`case_law`), `_fetched_at`, `title`,
`case_number`, `text` (full judgment), `date`, `url`, `court`, `jurisdiction`
(`PK-KP`), `country`, `language`, `category`, `headnote`, `year`.

## License

Public Domain (Government) — judgments of the Peshawar High Court are public
judicial records of the Government of Pakistan / Province of Khyber Pakhtunkhwa.
No formal open-data licence is published; standard government-publication
public-domain treatment applies. Commercial use: permitted.
