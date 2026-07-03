# VA/CodexCanonumOrientalium

**Codex Canonum Ecclesiarum Orientalium (CCEO)** — the 1990 Code of Canons of
the Eastern Churches, promulgated by Pope John Paul II through the Apostolic
Constitution *Sacri Canones* on 18 October 1990 (in force 1 January 1991).

It is the common code of canon law for the 23 *sui iuris* Eastern Catholic
Churches: 1546 canons organized in 30 titles. It is the Eastern counterpart to
the 1983 Latin *Codex Iuris Canonici* (covered separately as
`VA/CodexIurisCanonici`).

## Data Source

- **Index:** https://www.vatican.va/content/john-paul-ii/la/apost_constitutions/documents/hf_jp-ii_apc_19901018_index-codex-can-eccl-orient.html
- **Method:** Static HTML scraping of three official content pages
  (`...codex-can-eccl-orient-1.html` … `-3.html`).
- **Language:** Latin (official). The Vatican site does not host a free English
  translation of the CCEO, so this source captures the authoritative Latin text.

Each canon is parsed individually (`<b>Can. N</b> - …`) and emitted as one
record with the canon's full Latin body in the `text` field.

## Usage

```bash
# Connectivity / parse check
python3 bootstrap.py test

# Sample (~15 records to sample/)
python3 bootstrap.py bootstrap --sample

# Full run (streams all canons to data/records.jsonl)
python3 bootstrap.py bootstrap --full
# or the ingest-host alias:
python3 bootstrap.py bootstrap-fast --full
```

Coverage: ~1539 of 1546 canons (99.5%); a handful of vacant/renumbered canon
slots have no body text.

## License

[Public Domain (Holy See)](https://www.vatican.va/) — official Latin text of
canon law published by the Holy See on vatican.va. Commercial use permitted.
