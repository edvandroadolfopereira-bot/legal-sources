# UZ/MinjustRegistry — Departmental Normative Legal Acts (State Register)

Agency- and ministry-level normative-legal acts of the Republic of Uzbekistan that
must be registered in the **State Register of Departmental Normative Legal Acts**
held by the Ministry of Justice to take legal effect.

## Background

The MoJ registry page (`minjust.uz/en/interactive/reestrnpa/`) now redirects to the
unified **gov.uz** portal and exposes only registration metadata behind a SPA. The
authoritative **full text** of every registered departmental act is, however,
published on the official National Database of Legislation, **lex.uz**.

This source therefore harvests departmental acts from lex.uz, filtered to the
document forms that characterise departmental NPAs:

| form_id | Form (RU / UZ)            | Meaning      |
|---------|---------------------------|--------------|
| 486     | Приказ / Buyruq           | Order        |
| 487     | Положение / Nizom         | Regulation   |
| 488     | Правила / Qoidalar        | Rules        |
| 489     | Инструкция / Yo'riqnoma   | Instruction  |
| 490     | Указания                  | Directives   |
| 491     | Решение                   | Decision     |
| 575     | Регламент                 | Reglament    |
| 573     | Порядок / Tartib          | Procedure    |

This is **distinct from `UZ/LexUz`**, which covers primary legislation (laws, codes,
presidential decrees, cabinet resolutions).

## How it works

- **Search**: `https://lex.uz/ru/search/nat?form_id={id}` for each departmental form.
- **Full text, two layouts**:
  - *Older acts* are server-rendered HTML inside `<div id="divCont">` with semantic
    classes (`ACT_TEXT`, `BY_DEFAULT`, …). Russian pages are occasionally empty
    shells (act published only in Uzbek), so both language renderings are fetched and
    the one with more text is kept.
  - *Recent acts* are embedded text-based PDFs; the binary at `/pdffile/{id}` is
    downloaded and parsed with **PyMuPDF**.
- **Rate limit**: ~1 request/second.

## Fields

`_id`, `_source`, `_type` (`legislation`), `_fetched_at`, `title`, `text` (full body),
`date`, `doc_number`, `reg_number` (MoJ State Register number), `doc_type` (form),
`text_source` (`html` or `pdf`), `url`.

## Usage

```bash
python3 sources/UZ/MinjustRegistry/bootstrap.py bootstrap --sample
python3 sources/UZ/MinjustRegistry/bootstrap.py validate
```

## License

[Public domain (government)](https://lex.uz) — official normative-legal acts of the
Republic of Uzbekistan published on the National Database of Legislation (lex.uz).
Government legal texts are not subject to copyright; commercial use permitted.
