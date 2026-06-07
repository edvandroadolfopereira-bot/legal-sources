# BW/NBFIRA — Non-Bank Financial Institutions Regulatory Authority

Botswana's NBFIRA regulates insurance, pensions, capital markets, virtual assets,
and microlending. This source fetches regulatory publications and tribunal
judgements via the WordPress REST API.

## Data types

- **doctrine**: Public notices, circulars, enforcement actions, regulatory guidance
- **case_law**: Financial tribunal judgements (NBFIT cases)

## Strategy

WordPress REST API at `wp-json/wp/v2/`:
- `/posts` — public notices, news, circulars (~600+ records)
- `/tribunal-judgements` — tribunal decisions (~6 records with full text)

Full text is in `content.rendered` (HTML stripped to plain text). No PDF
extraction needed.

## License

[Public Government Documents (Botswana)](https://www.nbfira.org.bw/) — official
regulatory documents published for public compliance use. Attribution required.
