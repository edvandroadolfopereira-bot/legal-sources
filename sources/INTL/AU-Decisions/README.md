# INTL/AU-Decisions — African Union Assembly Decisions & Resolutions

Fetches decisions, declarations, and resolutions adopted by the African Union
Assembly of Heads of State and Government from the AU Digital Archives (DSpace).

## Data Source

- **URL**: https://archives.au.int/
- **Collection**: Assembly Collection (handle 123456789/19)
- **API**: DSpace REST API v6 at `/rest/collections/{uuid}/items`
- **Format**: Dublin Core metadata + PDF/text bitstreams
- **Records**: ~1,689 items (1964–2026)
- **Languages**: English, French, Arabic, Portuguese, Spanish, Swahili

## Strategy

1. Paginate through the Assembly Collection via DSpace REST API
2. For each item, extract Dublin Core metadata (title, date, type, reference)
3. Fetch pre-extracted text from TEXT bundle bitstreams (DSpace auto-extracts PDF text)
4. Fall back to downloading original PDF and extracting via pdfplumber if no TEXT bitstream

## License

[African Union open access](https://archives.au.int/) — AU archives are publicly accessible government documents. Attribution required.
