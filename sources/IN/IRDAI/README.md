# IN/IRDAI — Insurance Regulatory and Development Authority of India

Circulars, guidelines, and notifications from IRDAI, India's insurance regulator.

- **Circulars**: ~589 documents — regulatory instructions to insurers and intermediaries
- **Guidelines**: ~93 documents — detailed regulatory guidance
- **Notifications**: ~41 documents — gazette notifications, committee reconstitutions

All documents are PDFs with selectable text. Full text is extracted via pdfplumber.

## Strategy

Scrapes the IRDAI Liferay CMS listing pages (circulars, guidelines, notifications)
with pagination. Extracts PDF download URLs from table rows and downloads each PDF
for full text extraction.

## Usage

```bash
python bootstrap.py bootstrap --sample   # 15 sample records
python bootstrap.py bootstrap            # Full pull (~720 docs)
python bootstrap.py update               # First page of each category
python bootstrap.py test                 # Connectivity check
```

## License

[Government Open Data (India)](https://irdai.gov.in/) — Indian government regulatory documents are public records. No restrictions on access or use.
