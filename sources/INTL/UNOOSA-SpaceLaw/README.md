# INTL/UNOOSA-SpaceLaw

UN Office for Outer Space Affairs — Space Law Database. Full text of international space law instruments and select national space legislation.

## Data

- **5 UN Space Treaties**: Outer Space Treaty (1967), Rescue Agreement (1968), Liability Convention (1972), Registration Convention (1975), Moon Agreement (1979)
- **5 GA Resolution Principles**: Declaration of Legal Principles (1963), Direct Broadcasting Principles (1982), Remote Sensing Principles (1986), Nuclear Power Sources Principles (1992), Space Benefits Declaration (1996)
- **9 National Space Laws**: Germany, Netherlands, Norway, South Korea, South Africa (×2), Sweden (×2), Ukraine

Total: 19 documents with full text.

## Technical Notes

- All content is on static HTML pages at `www.unoosa.org`
- Uses `curl` subprocess with `--http1.1` and retry logic
- Content extracted from `#contentContainer` div via BeautifulSoup
- The ASTRO Angular SPA (astro.unoosa.org) has additional national legislation but is not programmatically accessible

## License

[UN Terms of Use](https://www.un.org/en/about-us/terms-of-use) — UN documents are generally freely reusable with attribution.
