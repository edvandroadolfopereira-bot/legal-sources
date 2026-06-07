# US/RegulationsGov — Federal Rulemaking Documents

Regulations.gov is the US federal government's portal for rulemaking documents —
rules, proposed rules, and notices published in the Federal Register.

## Data Coverage

- **Rules**: ~98K final rules from all federal agencies
- **Proposed Rules**: ~49K proposed rulemaking documents
- **Notices**: ~383K agency notices
- All documents with Federal Register cross-references include full text

## Data Access Strategy

1. **Regulations.gov API v4** (`api.regulations.gov/v4/documents`) — lists documents
   with metadata (agency, docket, dates, FR doc number). Requires API key; DEMO_KEY
   works with rate limits.
2. **Federal Register API** (`federalregister.gov/api/v1`) — provides full text
   body HTML using the FR document number. Free, no API key required.

## API Key

Set `REGULATIONS_GOV_API_KEY` env var for higher rate limits.
Default DEMO_KEY works but has low limits (~1000 req/hour).
Sign up free at: https://open.gsa.gov/api/regulationsgov/

## License

[US Public Domain](https://www.law.cornell.edu/uscode/text/17/105) — US federal government works are not eligible for copyright protection under 17 U.S.C. § 105.
