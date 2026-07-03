# GRECO Anti-Corruption Evaluation & Compliance Reports

**Source:** [https://www.coe.int/en/web/greco](https://www.coe.int/en/web/greco)
**Country:** CoE
**Data types:** doctrine
**Status:** Blocked

## Why this source is blocked

**Category:** Cloudflare protection

**Technical reason:** `cloudflare_waf`

**Details:** GRECO (Group of States against Corruption) publishes country evaluation, compliance, and addendum reports across multiple rounds for ~50 member states. The report PDFs are hosted on `rm.coe.int`, and the landing pages on `www.coe.int` — both return HTTP 403 via Cloudflare WAF (verified 2026-06-19, same block as `CoE/GRETAReports`). Unlike CPT, there is no HUDOC sub-database (e.g. `hudoc.greco.coe.int`) exposing this content via an accessible JSON API.

## How you can help

The site uses Cloudflare anti-bot protection that blocks automated/datacenter access.
- Browser automation (Playwright/Puppeteer) with stealth mode may work
- A residential proxy could bypass the datacenter IP block

- File an issue or open a PR at [worldwidelaw/legal-sources](https://github.com/worldwidelaw/legal-sources)

## License

[Council of Europe — Standard Disclaimer / Terms of Use](https://www.coe.int/en/web/portal/disclaimer) — CoE documents are reproducible for non-commercial purposes with attribution; commercial reuse may require consent. Flagged for review.
