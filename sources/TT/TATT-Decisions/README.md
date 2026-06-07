# TT/TATT-Decisions

Regulatory decisions, determinations, frameworks, spectrum plans, and consultation documents from the **Telecommunications Authority of Trinidad and Tobago (TATT)**.

## Data Source

- **URL**: https://tatt.org.tt/
- **Type**: WordPress REST API + PDF extraction
- **Documents**: ~300 (117 regulatory framework + 182 consultation)
- **Format**: PDF documents accessed via WordPress media API

## Strategy

The TATT website runs WordPress behind a Sucuri/Cloudproxy WAF. The scraper:

1. Solves the Sucuri JS cookie challenge (base64-decoded string concatenation)
2. Fetches `regulatory_framework` and `consultation` custom post types via WP REST API
3. Searches the WP media API for matching PDFs by title keywords
4. Downloads PDFs and extracts full text via pdfplumber

## License

[Public Domain — Government of Trinidad and Tobago](https://tatt.org.tt/) — government regulatory documents published for public access.
