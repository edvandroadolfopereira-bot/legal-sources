# SH/Courts — St Helena Senior Courts (BAILII)

Case law of the senior courts of St Helena, Ascension and Tristan da Cunha — a
self-governing British Overseas Territory — published on
[BAILII](https://www.bailii.org/sh/).

## Courts covered

| Code  | Court                          |
|-------|--------------------------------|
| SHSC  | Supreme Court of St Helena     |
| SHCA  | St Helena Court of Appeal      |

Both are the Senior Courts of the territory, sitting in Jamestown. Judgments are
published as HTML on BAILII with full text and `[YYYY] SHSC N` / `[YYYY] SHCA N`
neutral citations.

## Access notes

BAILII serves a [Anubis](https://github.com/TecharoHQ/anubis) proof-of-work bot
challenge to browser-like (`Mozilla/...`) User-Agents. A plain non-browser
User-Agent (`LegalDataHunter/1.0 (Open Data Research)`) is served the real
content directly, so no browser automation is required.

## Usage

```bash
python bootstrap.py test                 # connectivity check
python bootstrap.py bootstrap --sample   # fetch sample records
python bootstrap.py bootstrap            # full pull
```

## License

> ⚠️ **Commercial use restricted.** BAILII's terms restrict bulk and commercial
> reuse of its compiled database.

[BAILII Terms of Use](https://www.bailii.org/bailii/terms.html) — judgments are
Crown Copyright (UK Overseas Territory); BAILII provides free-of-charge access
with attribution required.
