# HT/CONATEL-Regulations — Conseil National des Télécommunications (Haiti)

Haiti's telecom legal and regulatory corpus, published by the Conseil National
des Télécommunications (CONATEL), the national telecom regulator.

## Coverage

- **Décret créant le CONATEL** (1969) and the **Loi organique**
- **Loi/Décret sur les télécommunications** (state monopoly decree, full text)
- **Décret sur la taxation** of telecom services
- **Décisions réglementaires** — regulatory decisions (those with a text layer;
  several are scanned image-only and are skipped)
- **Plan National de Numérotation** (PNN 2014)
- **Plan stratégique de transition vers la TNT** (digital TV transition)
- **Régime de concession radio** and **licensing procedures**
- **Formulaires** — official application forms for authorizations

Documents are PDFs hosted on the government domain (`conatel.gouv.ht`). Full text
is extracted with pdfminer. Scanned PDFs without a text layer are skipped (no OCR).
French language.

## Access

Drupal site; documents live under `/sites/default/files/*.pdf`, linked from
`/textes-r-glementaires`, `/node/113` (décisions), and individual `/node/` pages.
The scraper crawls these hub pages, follows document links one level deep, then
downloads and extracts each PDF.

## License

[Open Government Data](https://conatel.gouv.ht/) — official telecom regulator
documents published on the Haitian government domain (gouv.ht) for public access.
No explicit license deed; treated as open government data (commercial use permitted).
