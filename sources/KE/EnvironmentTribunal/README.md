# KE/EnvironmentTribunal — Kenya National Environment Tribunal (KENET)

Decisions of the National Environment Tribunal - Nairobi, fetched from the
Kenya Law platform (new.kenyalaw.org). ~155 decisions covering environmental
licensing appeals and impact assessments under EMCA.

## Data Access

- **Source:** https://new.kenyalaw.org/judgments/KENET/
- **Format:** Server-rendered HTML pages with AKN (Akoma Ntoso) structured content
- **Pagination:** `?page=N` query parameter
- **Full text:** Inline HTML — no PDF extraction needed
- **Rate limit:** 5s crawl delay (per robots.txt)

## Records

| Field   | Description                        |
|---------|------------------------------------|
| `_id`   | Unique ID derived from AKN path    |
| `title` | Case citation and parties          |
| `text`  | Full judgment text (cleaned HTML)  |
| `date`  | Decision date (ISO 8601)           |
| `url`   | Permalink on Kenya Law             |
| `court` | Court code (KENET)                 |

## License

[Public Domain (Government)](https://new.kenyalaw.org/about/) — Kenya Law publishes court and tribunal decisions as public domain government works.
