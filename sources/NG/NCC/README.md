# NG/NCC — Nigerian Communications Commission

The Nigerian Communications Commission (NCC) is the independent regulatory
authority for the telecommunications industry in Nigeria, established under the
Nigerian Communications Act 2003. Under Section 70 of the Act, the Commission is
empowered to make and publish regulations, guidelines, and determinations.

This source collects three categories of official NCC documents:

1. **Regulations** (legislation) — legally binding subsidiary legislation made
   under the NCA 2003, covering licensing, type approval, quality of service,
   consumer code of practice, interconnection, numbering, number portability,
   lawful interception, competition practices, spectrum fees, and more
   (published and draft).

2. **Guidelines** (doctrine) — official guidance documents on matters such as
   infrastructure deployment, dispute resolution, SIM replacement, co-location
   and infrastructure sharing, national roaming, spectrum trading, short codes,
   the Internet Code of Practice, and corporate governance (published and draft).

3. **Determinations** (doctrine) — regulatory decisions of the Commission on
   matters such as mobile voice termination rates, USSD pricing, interconnection
   rates, accounting separation, and market dominance.

All documents are PDF files hosted on the NCC website.

## Data access

- Each document is served as a PDF behind a stable `/media/{id}/view` URL.
- Listing pages group documents into published/draft sections; the scraper reads
  the anchor text as the title and downloads the linked PDF, extracting text with
  `pdfplumber`.
- Listing pages:
  - Regulations: `https://ncc.gov.ng/operators/regulations-guidelines/regulations`
  - Guidelines: `https://ncc.gov.ng/guidelines`
  - Determinations: `https://ncc.gov.ng/industry/regulations-guidelines/determinations`
- All PDFs are publicly accessible without authentication. A small number of
  older documents are scanned (image-only) PDFs with no extractable text layer;
  these are skipped.

## License

[Custom Terms (Government)](https://ncc.gov.ng/) — official Nigerian government
regulatory documents published by the NCC under the Nigerian Communications Act
2003 for public compliance. Regulations have force of law as subsidiary
legislation. Commercial use of the published material is permitted.
