# INTL/CAN-Gacetas — Gaceta Oficial del Acuerdo de Cartagena

Full-text supranational legislation of the **Comunidad Andina (CAN)**, published in
the *Gaceta Oficial del Acuerdo de Cartagena*. These instruments form the
*ordenamiento jurídico comunitario andino* and are directly binding on the member
states **Bolivia (BO), Colombia (CO), Ecuador (EC) and Peru (PE)**.

Document kinds covered (Strapi `group` slug → count as of 2026-06):

| Kind | Slug | ~Count |
|------|------|--------|
| Decisiones (Comisión / Consejo Andino) | `decisiones` | 982 |
| Resoluciones (Secretaría General) | `resoluciones` | 2601 |
| Dictámenes | `dictamenes` | 149 |
| Tratados y Protocolos | `tratados-y-protocolos` | 14 |

## Data access

The public site `comunidadandina.org` is a Next.js App Router app backed by a
Strapi CMS (`https://normativa.comunidadandina.org`). The Strapi REST API is
token-protected (HTTP 403), but the Next.js server exposes a **public,
token-injecting proxy**:

```
https://www.comunidadandina.org/api/normativa/?page=N&per_page=100&group=<slug>
```

It returns the Strapi `normative-documents` collection wrapped as
`{"data": {"data": [...], "meta": {"pagination": {...}}}}`. Each record carries a
`file` media object whose `url` (e.g. `/uploads/DECISION_966.docx`) is served from
`https://normativa.comunidadandina.org`.

Full document text is extracted from the attached file:
- `.docx` (the large majority) → `python-docx`
- `.pdf` → `pypdf`
- legacy `.doc` → best-effort (`antiword` / macOS `textutil` / pure-python OLE fallback)

Records whose file yields less than 200 characters of text are skipped (no
metadata-only records are emitted).

## Usage

```bash
# 15-record sample
python3 bootstrap.py bootstrap --sample

# full crawl → data/records.jsonl
python3 bootstrap.py bootstrap --full
```

## Record schema

`_id`, `_source`, `_type` (`legislation`), `_fetched_at`, `title`, `text`,
`date` (ISO `publication_date`), `url`, `nomenclature`, `document_kind`,
`gaceta`, `file_format`, `language` (`es`), `jurisdiction` (`INTL/CAN`),
`member_states`.

## License

[Andean Community Official Publication](https://www.comunidadandina.org/) — open
government data. Official supranational legislation of the Comunidad Andina
published in the Gaceta Oficial del Acuerdo de Cartagena. Commercial use permitted;
attribution to the Comunidad Andina recommended.
