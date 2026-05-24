# GN/CourSupremeLegislation — Guinea Supreme Court Legislative Texts

Legislative texts from the Cour Suprême de la République de Guinée.

Covers: codes in force, older codes, constitutions, laws, decrees, arrêtés.

- **Source:** https://www.coursupreme.org.gn/
- **Language:** French
- **Format:** PDF files embedded in WordPress posts, fetched via WP REST API
- **Volume:** ~90+ legislative texts across multiple categories

## Strategy

1. Query WP REST API for posts in legislation-related categories
2. Extract PDF URLs from post content HTML
3. Download PDFs and extract text via pypdf/pdfplumber
4. Skip scanned-image PDFs with no extractable text

## Categories Covered

- Textes législatifs (81 posts)
- Codes en vigueur (43 posts)
- Constitutions guinéennes (8 posts)
- Lois (16 posts)
- Décrets (6 posts)
- Arrêtés (3 posts)
- Codes anciens (7 posts)

Note: Posts may appear in multiple categories; deduplication by WordPress post ID.

## License

[Public Domain — Government of Guinea](https://www.coursupreme.org.gn/) — official government legislative publications. No explicit license stated; government legislative texts are presumed public.
