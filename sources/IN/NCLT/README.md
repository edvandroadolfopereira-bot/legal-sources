# IN/NCLT — National Company Law Tribunal

Insolvency and corporate resolution orders from NCLT, India's specialist tribunal for company law and IBC matters.

## Coverage

- **Benches**: 20+ across India (Mumbai, New Delhi, Chennai, Ahmedabad, Bengaluru, Kolkata, Hyderabad, etc.)
- **Case types**: IBC Admissions, Liquidation, Resolution Plans, Dissolution, Appointment of RP/Liquidator
- **Period**: 2017–present
- **Format**: PDF orders (digitally generated, text-extractable)

## Data Access

Uses IBBI's order aggregation portal:
1. Paginate through `https://ibbi.gov.in/orders/nclt?page=N` (20 orders per page)
2. Parse HTML table for case metadata and PDF download links
3. Download PDFs from `https://ibbi.gov.in/uploads/order/{hash}.pdf`

## License

[Government Open Data](https://ibbi.gov.in/) — Indian government tribunal decisions are public records. Attribution recommended.
