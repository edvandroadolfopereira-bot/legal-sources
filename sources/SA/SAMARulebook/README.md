# SA/SAMARulebook — Saudi Central Bank Rulebook

**Source:** https://rulebook.sama.gov.sa/
**Country:** Saudi Arabia (SA)
**Data type:** Legislation
**Language:** English
**Auth:** None (public access)

## Overview

The SAMA Rulebook is the Saudi Central Bank's comprehensive regulatory platform.
It contains full-text laws, implementing regulations, sector-specific rules,
guidance documents, and circulars organized by regulatory domain.

## Sections

| Section | ID | Description |
|---------|----|-------------|
| Laws & Implementing Regulations | 1361 | Core banking/finance laws |
| All Financial Institutions | 1362 | Cross-sector rules (AML, cyber, governance) |
| Banking Sector | 1363 | Bank-specific regulations |
| Finance Sector | 1365 | Finance company rules |
| Payment Systems & Providers | 1367 | Payment services regulations |
| Money Exchange Sector | 1366 | Money exchange rules |
| Credit Bureaus | 5902 | Credit bureau regulations |
| Regulatory Sandbox | 1368 | Sandbox framework |
| SAMA Circulars | 10291 | Regulatory circulars |

## Strategy

Crawls the Drupal book navigation structure starting from category pages.
Recursively discovers content pages and extracts full text from HTML.
No API available — pure HTML scraping with BeautifulSoup.

## Usage

```bash
python bootstrap.py bootstrap            # Full crawl
python bootstrap.py bootstrap --sample   # 15 sample records
python bootstrap.py test-api             # Connectivity test
```

## License

[Open Government Data](https://rulebook.sama.gov.sa/en/terms-and-conditions) — official SAMA regulatory content published for public compliance.
