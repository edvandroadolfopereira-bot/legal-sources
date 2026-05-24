# RW/BNR — National Bank of Rwanda Financial Regulations

Financial sector regulations from the National Bank of Rwanda (BNR), the
supervisor and regulator of financial institutions in Rwanda.

## Coverage

- Banking laws, regulations, directives, and guidelines
- Insurance and pension regulations
- Microfinance institution regulations
- Payment system regulations
- AML/CFT laws and guidelines
- Financial markets regulations
- Foreign exchange regulations
- Credit reporting system regulations
- Financial consumer protection
- Deposit guarantee fund regulations
- Trust and company service provider regulations
- Accreditation requirements
- Currency regulations
- Regulatory digests and market consultations

## Data access

The BNR website is a React SPA backed by JSON API endpoints. Each regulatory
category has a dedicated endpoint (e.g., `/banking_laws`, `/insurance_all`)
that returns a JSON array of documents with PDF download links.

Full text is extracted from PDFs using pdfminer.

## License

[Government open access](https://www.bnr.rw/disclaimer) — official financial
regulations published for public access. No restrictions on access.
