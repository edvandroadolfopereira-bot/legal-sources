# DK/KlagenaevnetUdbud — Klagenævnet for Udbud (Complaints Board for Public Procurement)

**Source:** [https://klfu.naevneneshus.dk/](https://klfu.naevneneshus.dk/)
**Country:** DK
**Data types:** case_law
**Language:** Danish
**Status:** Complete

## What this source provides

Klagenævnet for Udbud is the Danish administrative tribunal that decides
complaints about public procurement (public tenders). It publishes — as a
matter of principle — **all** of its final decisions (*kendelser*) from 1995
to the present. Approximately **1,695 board rulings** are available, each with
the **full decision text**.

## How it works

The public search portal at `klfu.naevneneshus.dk` is an Angular single-page
app backed by a public JSON API:

```
POST https://klfu.naevneneshus.dk/api/search
Content-Type: application/json

{"query": "", "types": ["ruling"], "skip": 0, "size": 50, "sort": "Descending"}
```

Each result record already contains the **full decision text** in the `body`
field (HTML). No per-document fetch or PDF extraction is required — the scraper
strips HTML tags, decodes entities, and emits clean plain text. Pagination is
via `skip`/`size`.

## Usage

```bash
# Fetch 15 sample records to sample/
python bootstrap.py bootstrap --sample

# Smoke test the API
python bootstrap.py test

# Fetch all records to data/records.jsonl
python bootstrap.py bootstrap --full
```

## Record schema

| Field | Description |
|-------|-------------|
| `_id` | `KLFU-<journal number>` |
| `title` | Case title (claimant *mod* defendant) |
| `text` | **Full text** of the decision |
| `date` | Decision date (ISO 8601) |
| `case_number` | Journal number (J.nr.), e.g. `25/09277` |
| `category` | Decision category (Materielle kendelser, Erstatningskendelser, …) |
| `authority` | Klagenævnet for Udbud |
| `is_brought_to_court` | Whether the decision was appealed to the ordinary courts |

## License

[Public domain — Danish Copyright Act § 9](https://www.retsinformation.dk/eli/lta/2014/1144) — no copyright.

The Danish Copyright Act (*Ophavsretsloven*) § 9 excludes laws, administrative
regulations, court judgments and **similar decisions of public authorities**
from copyright protection. Decisions of Klagenævnet for Udbud are such
public-authority decisions and are therefore in the public domain. Commercial
use is permitted; no attribution is required.
