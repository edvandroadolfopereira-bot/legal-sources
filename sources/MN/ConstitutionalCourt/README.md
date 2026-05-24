# MN/ConstitutionalCourt

Mongolia Constitutional Court (Монгол Улсын Үндсэн хуулийн цэц) — Decisions

## Source

Official website: https://constitutionalcourt.mn/

The Constitutional Court of Mongolia (Tsets) publishes its decisions on a WordPress site.
Two types of content are scraped:

1. **WP Posts** (categories 6+7): Court session reports containing decision digests
   (тойм) with substantive legal analysis — ~62 posts with decision content.
2. **WP Pages with PDF embeds**: Full decision texts as PDF documents embedded via
   DFLIP viewer (requires pdfminer for text extraction).

Decision types:
- **Магадлал** — Conclusions/Determinations
- **Дүгнэлт** — Opinions
- **Тогтоол** — Resolutions
- **Тойм** — Digests/Summaries of decisions

## Strategy

1. Fetch posts from decision categories (6=plenary, 7=standing committee) via WP REST API
2. Filter for posts with decision keywords in title and >500 chars of content
3. Extract and clean HTML content (strip Elementor CSS, HTML tags)
4. Optionally fetch WP pages with PDF embeds and extract text via pdfminer
5. Normalize into standard schema

## License

[Public Domain (Government)](https://constitutionalcourt.mn/) — official constitutional court decisions published in the public interest.
