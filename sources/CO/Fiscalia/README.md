# CO/Fiscalia — Fiscalía General de la Nación (Colombia)

Official communications and press releases from Colombia's Attorney General's Office (Fiscalía General de la Nación). 67,000+ documents covering organized crime prosecutions, corruption cases, human rights matters, environmental crime, and institutional announcements.

**Data type:** doctrine
**Coverage:** 2013–present
**Volume:** ~67,000 documents
**Access:** WordPress REST API (no authentication required)

## API

The Fiscalía website runs on WordPress. The WP REST API at `/wp-json/wp/v2/posts` provides paginated access to all posts with full HTML content.

- Endpoint: `https://www.fiscalia.gov.co/colombia/wp-json/wp/v2/posts`
- Pagination: `per_page=100&page=N` (max 100 per page)
- Fields: `id, date, title, content, link, categories`
- Total: ~67,658 posts (as of May 2026)

## License

[Open Government Data — Ley 1712 de 2014](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=56882) — Colombian transparency and access to public information law. Government publications are public information.
