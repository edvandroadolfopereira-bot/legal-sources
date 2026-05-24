# INTL/CODICES — Venice Commission Constitutional Case Law

The [CODICES](https://codices.coe.int/) database is maintained by the Venice Commission (Council of Europe). It contains ~10,000 constitutional court decisions from 100+ courts worldwide, with summaries in English and French and full texts in 43 languages.

## Data Access

REST JSON API at `https://codices.coe.int/api`:

- `POST /search` — paginated search (Page/Size params)
- `GET /precis/{guid}?lang=eng` — full précis with summary text
- `GET /tree?entityType=precis` — browse by region/country/court

## License

[Council of Europe Open Access](https://www.coe.int/) — open access research tool; attribution to Venice Commission required.
