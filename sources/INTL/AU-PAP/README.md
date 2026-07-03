# INTL/AU-PAP — African Union Pan-African Parliament

Resolutions, recommendations, model laws, activity reports, and hansards from the
Pan-African Parliament (PAP), the legislative body of the African Union.

**Source:** PAP Open Data Portal — https://opendata.pap.au.int/
**Documents:** ~230 (resolutions, recommendations, model laws, activity reports, hansards)
**Period:** 2004–present
**Languages:** English (primary), French, Portuguese, Arabic, Kiswahili, Spanish

## Data types

- `legislation` — resolutions, model laws
- `doctrine` — recommendations, activity reports, hansards

## Strategy

The PAP Open Data Portal (powered by Laws.Africa / PeachJam) publishes documents
using Akoma Ntoso URIs. Full text is rendered in `<la-akoma-ntoso>` HTML tags.

1. Paginate listing pages `/doc/{type}?page=N` to collect AKN URIs
2. Fetch each document page and extract text from the Akoma Ntoso markup
3. Extract metadata (title, date) from HTML and URI patterns

## License

[African Union Open Data](https://opendata.pap.au.int/about/) — open access institutional publications, attribution required.
