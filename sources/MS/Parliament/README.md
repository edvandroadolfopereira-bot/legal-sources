# MS/Parliament — Montserrat Legislative Assembly

Fetches legal documents from the Montserrat Legislative Assembly website at
[parliament.ms](https://parliament.ms/).

## Coverage

- **Acts** (88 documents)
- **Bills** (28 documents)
- **Laws** — consolidated statutes (217 documents)
- **Resolutions** (1 document)
- **SROs** — Statutory Rules and Orders (265 documents)

Total: ~599 documents with full text extracted from PDFs.

## Strategy

Uses the WordPress REST API (`/wp-json/wp/v2/legal_document`) to enumerate
all documents, fetches attached PDF media per document, and extracts full
text via pdfplumber.

## License

[Open Government Data](https://parliament.ms/) — official parliament records
published by the Montserrat Legislative Assembly. Government legislation is
public record.
