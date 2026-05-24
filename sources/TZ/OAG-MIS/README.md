# TZ/OAG-MIS — Tanzania Attorney General's Office Management Information System

Official legislation portal of the Attorney General's Office (AGO) of the
United Republic of Tanzania.

## Data Coverage

| Category | Count | Endpoint |
|----------|-------|----------|
| Parliament Acts | ~314 | `/portal/acts-ajax` |
| Subsidiary Legislation | ~4,479 | `/portal/legislation-ajax` |
| Revised Acts | ~542 | `/portal/revised-acts-ajax` |

All documents are available as downloadable PDFs with full text.

## Access Method

JSON/DataTables AJAX API with server-side pagination. No authentication required.
PDF download at `/portal/acts/{id}/download`, `/portal/legislation/{id}/download`,
and `/portal/revised-acts/revised/{id}/download`.

## License

[Open Government Data (Tanzania)](https://oagmis.oag.go.tz/) — Official government
legislation published by the Attorney General's Office for public access. Attribution
recommended.
