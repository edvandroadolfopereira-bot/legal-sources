# IN/CERC — Central Electricity Regulatory Commission

Orders, regulations, and tariff orders from India's Central Electricity
Regulatory Commission (CERC), the federal regulator for the electricity sector.

- **Coverage:** 2017–present (orders), 2004–present (regulations)
- **Volume:** ~4,800+ orders, ~200+ regulations
- **Format:** PDF documents linked from HTML index pages
- **Language:** English
- **Update frequency:** Daily (orders), periodic (regulations)

## Strategy

1. Parse year-based HTML index pages (`recent_orders{YEAR}.html`) for orders
2. Parse the consolidated regulations page (`Current_reg.html`)
3. Download PDF files and extract full text using pdfplumber
4. Normalize into standard schema with petition number, category, date, and full text

## License

[Government of India — Public Records](https://cercind.gov.in/) — Indian government regulatory orders and gazette notifications are public records. No access restrictions.
