# DO/TransparenciaSCJ — Dominican Republic Judicial Decisions

Judicial decisions from Dominican Republic courts via official open APIs.

## Data Source

Uses two official APIs from the Dominican Republic Poder Judicial:

1. **Juristeca API** (`api.poderjudicial.gob.do/Juristeca/api/v1/`)
   - Discovery and metadata for 500K+ judicial decisions
   - Searchable by keywords, paginated
   - Covers all courts: SCJ, Tribunal Constitucional, Appeals, First Instance

2. **Decisiones API** (`api.poderjudicial.gob.do/Decisiones/`)
   - Returns signed PDF URLs linked to case expediente numbers
   - PDFs hosted on Azure Blob Storage (sjdeposito.blob.core.windows.net)

## Pipeline

1. Search Juristeca for decisions containing "Expediente No."
2. Parse the expediente number from the title
3. Query Decisiones API with that number to get the PDF URL
4. Download PDF and extract full text via pdfplumber

## Coverage

- All Dominican courts (SCJ, TC, Cortes de Apelación, Primera Instancia, Juzgados de Paz)
- Decisions from ~2005 to present
- Language: Spanish
- Subject areas: Civil, Penal, Laboral, Comercial, Inmobiliario, Constitucional, Familia

## Usage

```bash
python bootstrap.py bootstrap --sample     # 12+ sample records
python bootstrap.py bootstrap              # Full bootstrap
python bootstrap.py update                 # Last 30 days
python bootstrap.py test-api               # Test API connectivity
```

## Rate Limits

Both APIs enforce 100 requests/minute per IP. The scraper uses conservative
1.5 req/s with retry logic for 429 responses.

## License

[Public Domain (Government)](https://justicia.gob.do/apis-judiciales/) — Official open APIs, no authentication required. Public judicial decisions published by the Dominican Republic Poder Judicial.
