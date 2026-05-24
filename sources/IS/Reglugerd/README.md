# IS/Reglugerd — Iceland Regulations Collection

Official database of all current Icelandic regulations (reglugerðir), maintained by
the government and published at [reglugerd.is](https://www.reglugerd.is/).

## Coverage

- ~14,467 regulations (base + amending)
- All Icelandic ministries
- Includes regulation text, publication date, ministry attribution
- Both current and historical regulations from 2000 onwards

## Data Access

1. **Listing**: GraphQL API at `island.is/api/graphql` — `getRegulations` query with pagination (30 per page, 483 pages)
2. **Full text**: HTML pages at `reglugerd.is/reglugerdir/allar/nr/{number}-{year}`

The old reglugerd.is domain (Eplica CMS) still serves full-text HTML, while the
island.is GraphQL provides structured listings.

## License

[Public Domain (Government)](https://www.government.is/) — Official Icelandic government
publications are public domain under Icelandic law (similar to § 9 of the Icelandic
Copyright Act, which excludes official legal texts from copyright protection).
