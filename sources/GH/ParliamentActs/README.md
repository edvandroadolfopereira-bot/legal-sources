# GH/ParliamentActs — Ghana Parliament Acts Database

Official institutional repository of the Parliament of Ghana, hosted on DSpace 7+.
Contains Acts of Parliament from 1960 onwards across multiple parliamentary eras.

## Data Source

- **URL**: https://repository.parliament.gh/
- **API**: DSpace 7 REST API (`/server/api/`)
- **Format**: JSON metadata + pre-extracted plain text from PDFs
- **Coverage**: ~990 Acts (1st Republic through 8th Parliament)
- **Language**: English

## Access Method

Uses the DSpace 7 REST API to:
1. List Acts communities (9 communities organized by Republic/Parliament era)
2. Discover items within each community via search endpoint
3. Fetch item metadata (title, date, author, subject)
4. Retrieve full text from TEXT bundle bitstreams (DSpace auto-extracts text from PDFs)

No authentication required. Rate limited to 1 request/second.

## License

[Open Government Data](https://repository.parliament.gh/) — Official Parliament of Ghana institutional repository, open access. Attribution required.
