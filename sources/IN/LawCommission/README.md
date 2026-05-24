# IN/LawCommission — Law Commission of India Reports

## Overview

All 289 Law Commission of India reports (1955–2024) across 22 commissions.
These are foundational policy and doctrine documents covering criminal law,
civil procedure, constitutional law, family law, tort, arbitration, and more.

- **Data type:** doctrine
- **Volume:** ~289 reports
- **Format:** PDF (newer reports have selectable text; older ones are scanned)
- **Auth:** none

## Strategy

1. Scrape the main listing page for 22 commission sub-page URLs
2. Scrape each commission sub-page for report metadata (number, title, date, PDF URLs)
3. Download PDFs and extract text via `common.pdf_extract`
4. Reports without extractable text are skipped

## Usage

```bash
python bootstrap.py bootstrap          # Full initial pull
python bootstrap.py bootstrap --sample # Fetch 15 sample records
python bootstrap.py update             # Fetch latest commission only
python bootstrap.py test               # Quick connectivity test
```

## License

[Government Open Data License — India](https://data.gov.in/government-open-data-license-india) — Indian government policy documents are public records.
