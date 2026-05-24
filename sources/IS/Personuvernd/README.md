# IS/Personuvernd — Icelandic Data Protection Authority

Persónuvernd is Iceland's supervisory authority for personal data protection,
publishing rulings (úrskurðir), decisions (ákvarðanir), and opinions (álit).

**URL:** https://island.is/s/personuvernd/urskurdir-akvardanir-og-alit
**Records:** ~1,237 decisions
**Language:** Icelandic
**Data type:** doctrine

## Data Access

Decisions are served via the island.is GraphQL API (`https://island.is/api/graphql`):
- List query: `getGenericListItems` with `genericListId: "18Qfx6UBAJmLrmaNZZA6lM"`
- Detail query: `getGenericListItemBySlug` with slug from list
- Content is in Contentful rich text format (nested document nodes)

## License

[Public Domain (official government decisions)](https://www.government.is/publications/) — Icelandic government decisions are public domain.
