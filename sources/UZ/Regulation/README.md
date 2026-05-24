# UZ/Regulation — Uzbekistan Draft Laws Public Discussion

**Source:** [regulation.gov.uz](https://regulation.gov.uz)

Portal for public discussion of draft normative-legal acts in Uzbekistan. Contains ~9,000 draft laws, cabinet resolutions, and regulatory documents with full text since 2015. Includes regulatory impact assessments and explanatory memoranda.

## Data

- **Type:** legislation (draft)
- **Documents:** ~9,000
- **Languages:** Uzbek, Russian
- **Coverage:** 2015–present
- **Content:** Full text of draft laws, cabinet resolutions, regulatory amendments, with explanatory notes and appendices

## Method

HTML scraping of listing pages (`/oz/document/index?page=N`) to discover document IDs, then fetching individual document pages (`/oz/d/{id}`) for full text and metadata.

## Fields

| Field | Description |
|-------|-------------|
| `_id` | `reg-{numeric_id}` |
| `title` | Document title |
| `text` | Full text of draft document |
| `date` | Publication/discussion start date |
| `end_date` | Discussion end date |
| `author` | Issuing authority |
| `document_type` | Type of document (resolution, law, etc.) |
| `comments_count` | Number of public comments |

## License

[Public domain (government)](https://regulation.gov.uz) — official government portal for public discussion of draft legislation. Open access, no registration required.
