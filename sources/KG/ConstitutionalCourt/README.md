# KG/ConstitutionalCourt — Kyrgyzstan Constitutional Court Decisions

**Source:** [constsot.kg](https://constsot.kg)
**Type:** case_law
**Records:** ~958 constitutional court decisions (1995–present)
**Language:** Russian, Kyrgyz

## Overview

The Constitutional Chamber of the Supreme Court of the Kyrgyz Republic publishes its decisions on a WordPress-based website. Decisions are uploaded as PDF documents and linked from post titles.

The WordPress REST API provides structured access to all decisions across sub-categories:
- Decisions (Решения) — 340
- Resolutions (Постановления) — 138
- Determinations (Определения) — 47
- Conclusions (Заключения) — 2
- Collegial Determinations (Определения коллегии) — 219

## Data Access

- **API:** `GET /kg/wp-json/wp/v2/posts?categories=4&per_page=100&page={N}`
- **Auth:** None required
- **Format:** JSON (WP REST API) + PDF attachments for full text
- **Pagination:** `X-WP-Total` / `X-WP-TotalPages` headers

## License

[Public Domain](https://constsot.kg) — government constitutional court decisions are public domain under Kyrgyz law.
