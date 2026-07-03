# US/PCAOB-Enforcement

PCAOB (Public Company Accounting Oversight Board) enforcement actions against registered audit firms and associated persons.

## Data

- **Type:** case_law (enforcement orders/sanctions)
- **Volume:** ~555 enforcement documents
- **Categories:** Settled Disciplinary Orders (500), Adjudicated Disciplinary Orders (28), Termination of Bars (27)
- **Full text:** Extracted from official PDF orders via pdfplumber
- **Access method:** HawkSearch API → PDF download → text extraction

## API

The PCAOB website uses HawkSearch for its enforcement actions listing:
- **Endpoint:** `POST https://essearchapi-na.hawksearch.com/api/v2/search/`
- **Client GUID:** `e962e95324cb46ef8955c0b09a3904b9`
- **Content type filter:** `contenttypelabel: "Enforcement Document"`
- **PDF documents:** Hosted on `assets.pcaobus.org`

## License

[US Public Domain](https://www.law.cornell.edu/uscode/text/17/105) — PCAOB is a nonprofit corporation established by Congress under the Sarbanes-Oxley Act. Enforcement orders are public records.
