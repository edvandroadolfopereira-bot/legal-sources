# FI/Kuluttajariitalautakunta — Finnish Consumer Disputes Board

Consumer dispute decisions from the Finnish Consumer Disputes Board (Kuluttajariitalautakunta).

- **Source**: https://www.kuluttajariita.fi/paatokset/
- **Type**: case_law
- **Records**: ~1,255 decisions
- **Coverage**: Consumer disputes (vehicles, housing, travel, banking, etc.)
- **API**: WordPress REST API — `/wp-json/wp/v2/paatos`
- **Language**: Finnish

## Strategy

Uses the public WordPress REST API endpoint for the custom post type `paatos`.
Paginated with `per_page=100` and `page` parameter. Full HTML content stripped
to plain text. Decision numbers extracted from the `yoast_head_json` metadata
or from content body.

## License

[Public Domain (Government)](https://www.finlex.fi/en/open-data/) — Official Finnish government decisions are public domain.
