# INTL/UNCITRAL-EnactmentStatus — UNCITRAL Model Law Enactment Status Tables

**Source:** [https://uncitral.un.org/en/texts](https://uncitral.un.org/en/texts)
**Data types:** legislation

## Overview

Each record is the authoritative "Status" page maintained by the UNCITRAL
Secretariat for one model law or convention. The page lists every State (and,
where relevant, sub-jurisdiction such as Australian or Canadian provinces and
Hong Kong/Macao) that has enacted the model law or become a party to the
convention, together with the year and footnotes describing reservations,
declarations, and local modifications.

This complements the sibling sources:

- `INTL/UNCITRAL-Texts` — the model-law / convention text itself
- `INTL/UNCITRAL-CLOUT` — case law applying those texts

The full body text of each status page (intro paragraph + enactment table +
footnotes) is captured in the `text` field; the table is additionally parsed
into a structured `entries` list (`state`, `year`, `notes`).

Coverage: ~20 instruments including the Model Law on International Commercial
Arbitration, the Model Law on Electronic Commerce, the CISG, the Model Law on
Cross-Border Insolvency, the Singapore Convention on Mediation, and more.

## How it works

1. Crawl the 12 subject category pages under `/en/texts/{category}` to discover
   instrument pages.
2. On each instrument page, follow the "Status" link (`{instrument}/status`).
3. Parse each status page: title (`<h1>`), intro, enactment table, footnotes.
4. Dedup by normalized title (a few URL paths alias to the same status page).

## License

[UN Terms of Use](https://www.un.org/en/about-us/terms-of-use) — UNCITRAL status
tables are official UN documents. Personal, non-commercial use permitted.
Reproduction for resale or redistribution requires written permission from the UN.

> ⚠️ **Commercial use restricted.** See terms.
