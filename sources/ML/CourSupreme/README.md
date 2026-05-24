# ML/CourSupreme — Mali Supreme Court (Cour Suprême)

Mali Supreme Court decisions sourced from Juricaf (AHJUCAF francophone court
decisions database). ~1,022 decisions from 1993 to present.

- **Source**: https://juricaf.org
- **Format**: JSON API (listing) + HTML (full text)
- **Coverage**: ~1,022 decisions, 1993–2025
- **Language**: French
- **Data type**: case_law

## How it works

1. Queries the Juricaf JSON API for paginated Mali Supreme Court decision listings
2. Fetches each individual decision page for full text from `div#textArret`
3. Extracts Dublin Core metadata (title, date, court, docket number)
4. Normalizes into standard schema with full text

## License

[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) — Open Database License. Attribution and share-alike required. Commercial use permitted.
