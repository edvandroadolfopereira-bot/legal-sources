# IN/DRAT — Debt Recovery Tribunals & Appellate Tribunals

Orders from India's 39 Debt Recovery Tribunals (DRTs) and 5 Debt Recovery
Appellate Tribunals (DRATs), accessed via the public e-DRT API at drt.gov.in.

## Data

- **Type:** case_law (daily orders, interim orders, final orders)
- **Coverage:** Banking debt recovery under RDDBFI Act, SARFAESI Act, and IBC
- **Tribunals:** 44 total (39 DRTs + 5 DRATs) across India
- **Period:** ~2020–present (electronic records)
- **Language:** English and Hindi

## Access Method

Public REST API at `https://drt.gov.in/drtapi` using multipart/form-data POST.
No authentication required. Key endpoints:

| Endpoint | Purpose |
|----------|---------|
| `getDrtDratScheamName` | List all tribunals |
| `getDrtDratCaseTyepName` | Case types per tribunal |
| `getDrtDailyOrderReportCaseNo` | Daily orders by case number |
| `getDrtFinalOrderReportCaseNo` | Final orders by case number |

Orders are PDFs served from `cis.drt.gov.in`. Text extraction via pdfplumber.
Some tribunals upload scanned-image PDFs (no extractable text without OCR).

## License

[Indian Government Public Data](https://drt.gov.in/) — Government tribunal
orders are public records. Open access via official e-DRT portal.
