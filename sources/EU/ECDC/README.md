# EU/ECDC — European Centre for Disease Prevention and Control

Publications from ECDC including rapid risk assessments, threat assessment briefs,
epidemiological updates, technical reports, and guidance documents.

**Data type:** doctrine
**Coverage:** 2005–present
**Estimated volume:** 1000+ publications

## Approach

1. Collect all publication URLs from the ECDC sitemap (`/sitemap.xml`)
2. For each publication page under `/en/publications-data/`:
   - Extract inline body text from HTML
   - If body text is minimal (<500 chars) and a PDF link exists, download and extract text from PDF
3. Normalize to standard schema

## License

[ECDC Copyright and Reuse Policy](https://www.ecdc.europa.eu/en/copyright) — reproduction permitted with source acknowledgement.
