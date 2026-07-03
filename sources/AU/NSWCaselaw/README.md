# AU/NSWCaselaw — New South Wales Caselaw

Full-text judgments and decisions of the **New South Wales courts and
tribunals**, published by the official NSW Caselaw service
(https://www.caselaw.nsw.gov.au/).

Coverage spans, among others:

- Court of Appeal (NSWCA)
- Court of Criminal Appeal (NSWCCA)
- Supreme Court (NSWSC)
- District Court (NSWDC)
- Land and Environment Court (NSWLEC)
- NSW Civil and Administrative Tribunal (NCAT — NSWCATCD, NSWCATOD, …)

## Data source & strategy

NSW Caselaw publishes each decision as full-text HTML behind a session-driven
search UI. The complete corpus is also mirrored as an **ungated, openly
redistributable HuggingFace dataset** —
[`corto-ai/nsw-caselaw`](https://huggingface.co/datasets/corto-ai/nsw-caselaw)
(~27,453 decisions harvested directly from `caselaw.nsw.gov.au`). Each row
carries the full plain-text judgment plus its medium-neutral citation,
court/jurisdiction, decision date, word count and the canonical decision id.

`bootstrap.py` reads the dataset through the HuggingFace **datasets-server rows
API** (no auth, paginated, no IP blocking) and reconstructs the canonical
`https://www.caselaw.nsw.gov.au/decision/<id>` URL for every record so users can
link back to the authoritative source.

Each normalized record contains:

| field | description |
|-------|-------------|
| `_id` | `AU-NSW-<decision id>` |
| `title` / `citation` | medium-neutral citation, e.g. `R v Botrus (No 3) [2020] NSWSC 1448` |
| `text` | **full decision text** (typically 40k–140k chars) |
| `court_code` | court suffix parsed from the citation (NSWSC, NSWCA, …) |
| `doc_type` | `decision` |
| `jurisdiction` | `new_south_wales` |
| `date` | ISO 8601 decision date |
| `url` | canonical caselaw.nsw.gov.au decision URL |

## Usage

```bash
python bootstrap.py test                 # connectivity check
python bootstrap.py bootstrap --sample   # 15 sample records -> sample/
python bootstrap.py bootstrap --full     # all records -> data/records.jsonl
python bootstrap.py bootstrap-fast       # alias for --full (VPS runner)
```

## License

[Copyright in Judicial Decisions Notice 1995 (NSW)](https://www.caselaw.nsw.gov.au/policy.html) — attribution requested; commercial use permitted.

Copyright in NSW judicial decisions resides in the State of New South Wales, but
the *Copyright in Judicial Decisions Notice 1995 (NSW)* authorises **any person
to reproduce, publish and otherwise deal with any judicial decision**, provided
that third-party law-report editorial material (e.g. publisher headnotes) is not
reproduced without further authority. The judgment bodies captured by this
source are the courts' own text, so commercial reuse with attribution is
permitted.
