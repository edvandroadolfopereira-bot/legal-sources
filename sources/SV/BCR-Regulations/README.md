# SV/BCR-Regulations — Banco Central de Reserva de El Salvador (Regulations)

Full text of the technical regulatory framework (*marco normativo*) governing
El Salvador's financial system, issued by the **Comité de Normas del Banco
Central de Reserva (BCR)**.

This covers *normas técnicas* (prudential, accounting and general), reglamentos,
instructivos, lineamientos and resoluciones that apply to banks, insurers, the
pension system (AFP/SAP), the securities market and other supervised entities.

- **Publisher:** Banco Central de Reserva de El Salvador (Comité de Normas)
- **Portal:** https://www.bcr.gob.sv/regulaciones/
- **Language:** Spanish
- **Type:** doctrine (regulatory/technical norms of a public authority)

## How it works

1. Each norm's detail is served by a POST to
   `https://www.bcr.gob.sv/regulaciones/normativa.php` with `norma=<numeric id>`,
   returning the Referencia (e.g. `NCF-13`), title, Objeto, approval date,
   effective date and approving body.
2. The full-text PDF for each norm lives at a predictable URL:
   `https://www.bcr.gob.sv/regulaciones/upload/<Referencia>.pdf`.
3. The scraper enumerates the numeric ids (backing DB tops out ~1000), downloads
   each linked PDF and extracts its text. Scanned/empty PDFs (no text layer) are
   skipped.

## Usage

```bash
# Fetch a validation sample (14 text-bearing norms)
python bootstrap.py bootstrap --sample

# Full bootstrap (all norm ids)
python bootstrap.py bootstrap

# Quick connectivity test
python bootstrap.py test-api
```

## Record schema

Each normalized record contains `_id`, `_source`, `_type` (`doctrine`),
`_fetched_at`, `title`, `text` (full norm text), `date`, `url`, plus
`reference`, `objeto`, `approval_date`, `effective_date`, `approved_by`,
`regulatory_status`, `jurisdiction`, `language` and `publisher`.

References containing `-C-` are consultation drafts (*en consulta*) and have no
effective/approval date until enacted; their full text is still captured.

## License

[Open Government Data](https://www.bcr.gob.sv/) — official regulations issued by
a public authority (the central bank of El Salvador). Official legal/regulatory
texts of the state; commercial use permitted.
