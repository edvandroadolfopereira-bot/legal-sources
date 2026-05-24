# BW/BOB-Regulations — Bank of Botswana Regulations & Directives

Banking legislation, regulations, prudential guidelines, circulars, and directives
from the Bank of Botswana.

## Coverage

- Banking Act 2023 and predecessor legislation
- Banking Regulations 2025
- Credit Information Act and Regulations
- Financial Intelligence Act and Regulations
- Basel capital adequacy directives
- Prudential guidelines (corporate governance, cybersecurity, AML/CFT, etc.)
- Circulars to banks

~47 PDF documents; ~15-20 extractable (remainder are scanned image PDFs).

## Strategy

1. Scrape 5 regulatory section pages for PDF links
2. Download each PDF
3. Extract full text with pdfplumber
4. Uses curl subprocess for HTTPS (system Python SSL too old for this server)

## License

Public government regulatory documents published by the Bank of Botswana
for compliance and public information purposes. No explicit open data license
published, but documents are freely downloadable from the official website.
