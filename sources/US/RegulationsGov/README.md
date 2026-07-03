# US/RegulationsGov — Federal Rulemaking Documents

Regulations.gov is the US federal government's portal for rulemaking documents —
rules, proposed rules, and notices published in the Federal Register. The full text
of every one of those documents is published in the **Federal Register**, whose API
is free and keyless, so this source draws both its listing and its full text from
the Federal Register API.

## Data Coverage

- **Rules** (legislation): ~230K final rules from all federal agencies since 1994
- **Proposed Rules** (legislation): ~120K proposed rulemaking documents
- **Notices** (doctrine): ~600K+ agency notices
- **Presidential Documents** (doctrine): proclamations, executive orders, etc.
- Every document includes full text from the Federal Register.

## Data Access Strategy

**Federal Register API v1** (`federalregister.gov/api/v1/documents.json`) — free, no
API key required. The scraper lists documents by type and short publication-date
windows (5 days, to stay under the API's 2,000-result deep-pagination cap), iterating
newest-first back to the 1994 digital archive. Full text comes from each document's
`raw_text_url` (HTML body fallback).

> **Note:** This source previously listed documents through the Regulations.gov API
> v4, but under the shared `DEMO_KEY` that API is capped at ~25 requests/hour, so a
> full run only ever retrieved the first page of 25 records (issue #944). The
> Federal Register API has no such limit and contains the same full text.

## License

[US Public Domain](https://www.law.cornell.edu/uscode/text/17/105) — US federal government works are not eligible for copyright protection under 17 U.S.C. § 105.
