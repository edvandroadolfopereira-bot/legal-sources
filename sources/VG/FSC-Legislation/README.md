# BVI Financial Services Legislation (VG/FSC-Legislation)

**Source:** [https://www.bvifsc.vg/library/legislation](https://www.bvifsc.vg/library/legislation)
**Country:** VG (British Virgin Islands)
**Data types:** legislation
**Language:** English

## What this source provides

Consolidated, revised-edition **full text** of the principal British Virgin
Islands financial-services and corporate statutes, published as PDFs by the BVI
Financial Services Commission (FSC). This is the high-signal corpus for
offshore-company and financial investigations:

- BVI Business Companies Act
- Insolvency Act
- Securities and Investment Business Act
- Financial Services Commission Act
- Regulatory Code
- Beneficial Ownership Secure Search System (BOSS) Act
- Anti-Money Laundering Regulations + Code of Practice
- Proceeds of Criminal Conduct Act
- Limited Partnership / Partnership / Trustee / Special Trusts Acts
- Banks and Trust Companies Act, Company Management Act
- Financing and Money Services Act, Insurance Act, Mutual Funds Regulations

## Access method

The FSC legislation **index and detail HTML pages are behind Cloudflare** and
return a challenge shell to headless clients, so the catalogue cannot be
crawled. The **PDF files themselves** (`/sites/default/files/{slug}.pdf`) are
served directly and download cleanly with the project User-Agent. The scraper
therefore uses a **curated list of verified PDF slugs** (see `bootstrap.py`),
downloads each PDF, and extracts full text via the shared `pdf_extract` backend.

Revised editions reuse the same slug, so the list is stable across re-runs. If
the FSC drops the Cloudflare gate on the index, this can be upgraded to a full
crawl.

## License

[Crown Copyright (British Virgin Islands)](https://www.bvifsc.vg/library/legislation) — official BVI legislation published by the Financial Services Commission for free public access. Statute text is freely reproducible as official law; no formal open licence is specified. Commercial use permitted.
