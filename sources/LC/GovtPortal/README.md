# LC/GovtPortal — Saint Lucia Government Legislation Portal

Fetches legislation from the Government of Saint Lucia web portal at
<https://www.govt.lc/legislations>.

## Coverage

~103 documents including:
- Constitution of Saint Lucia
- Criminal Code, Labour Code
- Tax acts (VAT, Income Tax, Excise, Customs)
- Public Health Act and regulations
- Insurance, Banking, and Financial Acts
- Education Act, Police Act
- Collective agreements (government–union)
- Bills and statutory instruments

## Strategy

1. Call `/api/services.asmx/GetResourceSummaries` JSON API to list all items
2. Download each PDF from `media.govt.lc`
3. Extract full text via pdfplumber
4. Skip non-PDF files (DOCX/DOC — 3 items)

## License

[Open Government Data](https://www.govt.lc/) — official government publications,
freely available on the government portal. No explicit license stated; treated as
open government data.
