# PK/BalochistanCode — Balochistan Laws (Provincial Legislation)

Official online code of the Province of Balochistan, Pakistan, published by the
**Balochistan Law & Parliamentary Affairs Department** at
[balochistancode.gob.pk](https://balochistancode.gob.pk/).

Covers ~1,700 substantive **acts, ordinances, rules and subordinate/delegated
legislation**. This source completes the Pakistan provincial code set already
covered for Punjab, Sindh and Khyber Pakhtunkhwa.

## How it works

1. Fetch the alphabetical listing `/laws_rules.aspx?wise=alphabetical&opento=1`,
   which embeds an HTML-escaped blob of all law entries (title, act number,
   promulgation date, status) each linking a viewer URL
   `/Document.aspx?wise=opendoc&docid=<N>&docc=<M>`.
2. Resolve each viewer page to its underlying full-text PDF at
   `/lawdir/<uuid>.pdf`.
3. Download the PDF and extract full text with `pdfplumber`.

A minority of entries are legacy `.doc` uploads (title ends in `.doc`) whose
viewer does not yield a text-extractable PDF; those are skipped.

`_type`: `legislation` · `jurisdiction`: `PK-BA` · language: English.

## Usage

```bash
python bootstrap.py bootstrap --sample        # ~12 sample records
python bootstrap.py bootstrap                 # all laws -> data/records.jsonl
python bootstrap.py bootstrap-fast --sample   # VPS pipeline alias
python bootstrap.py updates --since 2024-01-01
```

## License

[Public Domain (Government)](https://balochistancode.gob.pk/) — acts, ordinances
and rules of the Province of Balochistan are public legislative records of the
Government of Pakistan / Province of Balochistan. No formal open licence is
published; standard government-publication public-domain treatment applies.
Commercial use permitted.
