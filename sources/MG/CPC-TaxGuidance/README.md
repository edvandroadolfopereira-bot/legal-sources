# MG/CPC-TaxGuidance — Madagascar DGI Tax Administrative Doctrine

Administrative tax doctrine from Madagascar's Direction Générale des Impôts (DGI),
published on the official "Textes Réglementaires" portal at
[portal.impots.mg/textes](https://portal.impots.mg/textes/).

## Coverage

- **Document types**: Notes, Circulaires, Instructions, Décisions, Avis, Communiqués, Filazana
- **Date range**: 2004–present (~260 doctrine documents)
- **Languages**: French, Malagasy
- **Full text**: Extracted from born-digital PDFs via pdfplumber/PyMuPDF/pdfminer

Pure legislation on the same portal (CGI, CPF, lois, décrets, arrêtés) is excluded
from this doctrine source.

## Data Access

The portal loads document listings via AJAX POST to `modele/req_filter.php`.
Each document has a downloadable PDF. Full text is extracted from the PDF.

**Note**: The host uses an incomplete TLS certificate chain; requests use `verify=False`.

## License

[Open Government Data](https://portal.impots.mg/textes/) — official administrative
tax texts published by the Madagascar DGI for public use ("Publique" visibility).
No explicit open license stated; treated as open government data.
