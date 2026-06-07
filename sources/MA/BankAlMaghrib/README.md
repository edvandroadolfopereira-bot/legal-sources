# MA/BankAlMaghrib — Bank Al-Maghrib Circulars & Regulations

Bank Al-Maghrib (BAM) is Morocco's central bank. This source collects
regulatory documents published on **bkam.ma**: circulars, directives,
instructions, recommendations, and banking laws.

## Coverage

- **Categories**: Prudential regulation, payment systems, forex, money
  market, banking law, participative banking, microfinance, interest rates,
  fiduciary activity
- **Document types**: Circulars, directives, arrêtés, instructions, laws
- **Languages**: French (primary), Arabic
- **Period**: ~1993–present

## Strategy

1. Crawl all regulation category pages under `/Trouvez-l-information-concernant/Reglementation/`
2. Extract PDF download links (`/content/download/...`)
3. Download each PDF and extract text with pdfplumber/PyPDF2
4. Skip scanned-image PDFs that yield no extractable text (~77% of corpus)
5. Normalize remaining documents (~60+ with full text)

## License

[Legal Notice](https://www.bkam.ma/en/Find-information-about/Legal-notice) — official central bank regulatory publications, open access.
