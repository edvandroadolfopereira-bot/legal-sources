# SR/DNAWetgeving — Suriname Parliament Legislation (DNA)

Suriname laws from De Nationale Assemblee (DNA). Covers pre-2005 consolidated
texts and post-2005 enacted laws.

- **Source**: https://www.dna.sr/wetgeving/
- **Format**: HTML index + PDF downloads
- **Coverage**: ~186 pre-2005 consolidated laws (text-extractable PDFs)
- **Language**: Dutch
- **Data type**: legislation

## How it works

1. Scrapes index pages for law links (pre-2005 consolidated and post-2005)
2. Fetches each law page to find PDF download URL
3. Downloads PDF and extracts text via pypdf
4. Only includes laws where text extraction yields 100+ characters

## License

Public domain — Suriname government legislation.
