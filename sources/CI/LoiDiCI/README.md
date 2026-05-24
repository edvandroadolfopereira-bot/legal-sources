# CI/LoiDiCI — Côte d'Ivoire Legal Codes

Côte d'Ivoire legal codes and legislation published article-by-article via
WordPress at [loidici.biz](https://loidici.biz/). Covers 30+ legal codes
(Civil, Penal, Labor, Constitution, Electoral, Maritime, etc.) plus court
decisions. ~15,500 posts, content in French.

## Data Access

Uses the WordPress REST API:
- `GET /wp-json/wp/v2/posts?per_page=100&page=N` — paginate all posts
- `GET /wp-json/wp/v2/categories?per_page=100` — list categories
- Full text available in `content.rendered` field (HTML)

## License

> ⚠️ **Site claims "all rights reserved" on compilation.**

The underlying legal texts (codes, laws, decrees, court decisions) are official
government acts of Côte d'Ivoire and are generally not subject to copyright.
The site operator claims copyright over the compilation/formatting, but the
statutory text content itself is public domain.

[Public Domain (Government Acts)](https://loidici.biz/) — official legal texts
are not copyrightable under most legal systems.
