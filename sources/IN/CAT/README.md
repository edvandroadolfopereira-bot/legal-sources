# IN/CAT — Central Administrative Tribunal

Final orders and judgments from the Central Administrative Tribunal (CAT), India.

## Overview

CAT is a statutory body established under Article 323-A of the Indian Constitution
to adjudicate service-related disputes for central government employees. It has
19 benches across India and has disposed of 800,000+ cases since 1985.

## Data Source

- **Portal**: CIS (Case Information System) at `cis.cgat.gov.in`
- **Endpoint**: `fiorder_detail.php` — date-wise final orders per bench
- **Format**: HTML table listing + PDF judgments
- **Coverage**: Final orders/judgments with PDF attachments
- **Auth**: None required

## Strategy

1. Iterate over all 19 benches
2. Query date-wise final orders in monthly chunks (dd/mm/yyyy format)
3. Parse HTML table for case number, parties, and PDF links
4. Download PDFs and extract full text using pdfplumber
5. Normalize into standard schema

## License

[Government Open Data](https://cgat.gov.in/) — Indian government tribunal decisions are public records. Attribution required.
