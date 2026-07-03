# CV/JurisprudenciaCV — Cabo Verde Jurisprudence (CSMJ ECLI Portal)

Official ECLI jurisprudence database of the **Conselho Superior da Magistratura
Judicial de Cabo Verde** (CSMJ), aggregating decisions from **all** Cape Verde
superior courts:

- Supremo Tribunal de Justiça
- Tribunal da Relação de Barlavento
- Tribunal da Relação de Sotavento

Source: <https://jurisprudencia.cv/>

## Data access

The portal is a dynatable-backed app that loads decisions from a clean JSON
endpoint:

```
GET https://jurisprudencia.cv/items/loadItems?offset=0&perPage=250&page=1
```

Each record provides the ECLI, court (`tribunal`), judge-rapporteur (`relator`),
decision date (`dataAcordao`, `DD/MM/YYYY`), thematic area (`tematica`) and the
official **complete headnote** (`sumarioCompleto`). The sumário is the published
unit of jurisprudence for these courts — there is no separate public full-text or
PDF — so it serves as the document `text` (consistent with how the project treats
other ECLI/sumário case-law sources). Records without a substantive headnote
(~70% are metadata-only) are skipped.

Total catalogue: ~1,296 decisions; ~390 carry a substantive headnote. The host's
TLS chain is incomplete, so requests use `verify=False`.

## Usage

```bash
python3 bootstrap.py bootstrap --sample     # 15 sample records -> sample/
python3 bootstrap.py bootstrap-fast --full  # full run -> data/records.jsonl
python3 bootstrap.py updates --since 2020-01-01
```

## License

[Public Domain](https://jurisprudencia.cv/) — official judicial decisions of the
Republic of Cabo Verde, published by the CSMJ. Commercial use permitted; no
attribution required.
