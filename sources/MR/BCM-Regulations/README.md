# MR/BCM-Regulations — Banque Centrale de Mauritanie

Banking laws, prudential regulations, monetary policy instructions, and circulars
from the Central Bank of Mauritania.

## Data source

- **Publisher:** Banque Centrale de Mauritanie (BCM)
- **URL:** https://www.bcm.mr/
- **Backend:** Drupal 11 JSON:API at `bo.bcm.mr`
- **Language:** French
- **Coverage:** Banking laws, instructions, circulars, ordonnances (2007–present)

## How it works

The BCM website is a React SPA backed by a Drupal JSON:API. The scraper:

1. Queries page nodes containing legal texts (nodes 810, 811, 825, 828, 898, 899, 904, 948)
2. Extracts PDF links from the HTML content fields
3. Downloads and extracts full text from PDFs via pdfplumber
4. Also captures inline HTML legal text from pages without PDFs

Some PDFs are scanned images and fail text extraction (~40% of PDFs).
The remaining PDFs plus inline text provide sufficient coverage.

## License

[Public domain (government)](https://www.bcm.mr/) — Official Mauritanian government
banking legislation and regulations. No explicit license published; standard government
publication rules apply.
