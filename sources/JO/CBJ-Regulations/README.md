# JO/CBJ-Regulations — Central Bank of Jordan (Regulations & Circulars)

English-language legal corpus published by the **Central Bank of Jordan (CBJ)**:

- **Laws** — the Banking Law, the Central Bank of Jordan Law, the Money Exchange
  Business Law, the Electronic Transactions Law, the Credit Information Law, etc.
- **Payment Systems Legislation** — payment-system laws and the circulars and
  instructions issued under them.
- **Regulations & Instructions** — prudential, capital, AML/CFT, governance and
  consumer-protection instructions to licensed banks.
- **Circulars** — supervisory circulars to banks.
- **Guidelines & Frameworks** — supervisory guidance documents.

## Source

- Website: https://www.cbj.gov.jo/
- Document-library listing pages: `https://www.cbj.gov.jo/EN/List/{category}`
  (e.g. `/EN/List/Laws`, `/EN/List/Circulars`).
- Each listing row pairs a title with a download link to a PDF stored under
  `/ebv4.0/root_storage/en/`.

## Method

`bootstrap.py` parses each English category listing page, downloads each linked
PDF, and extracts full text via `common.pdf_extract` (opendataloader-pdf →
pdfplumber → pypdf). Records whose PDF yields no usable text (scanned image-only
documents) are skipped. Records are deduplicated by PDF URL. Publication dates
are parsed from the document titles when present (`dated DD/MM/YYYY` or
`... of YYYY`).

`_type` follows the publisher's own grouping: items in the *Laws* and *Payment
Systems Legislation* categories are typed `legislation`; instructions, circulars
and guidelines are typed `doctrine`.

## License

[Open Government Data — Central Bank of Jordan](https://www.cbj.gov.jo/) — official
central-bank laws, regulations, instructions and circulars published by a Jordanian
government authority for public access. No formal open-license deed is published;
treated as open government data (commercial use permitted for official legal texts).
