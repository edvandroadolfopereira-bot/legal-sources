# CR/BCCR-Regulations — Banco Central de Costa Rica, Marco Legal

Full text of the **Central Bank of Costa Rica (Banco Central de Costa Rica,
BCCR)** regulatory framework ("Marco Legal").

## What this source covers

- **Reglamentos** — e.g. Reglamento del Sistema de Pagos, Reglamento SINPE-TP,
  Reglamento de sistemas de tarjetas de pago, Código de Gobierno Corporativo,
  internal operating regulations (~44 documents).
- **Normativa** — norms on recognition of foreign institutions and
  international-reserve operations.
- **Acuerdos de la Junta Directiva** — board agreements and resolutions
  (the bulk, ~290+ documents, including historical 2010–2019 and pre-2010).
- **Control gacetario** — official-gazette publication records.

## Data access

`bccr.fi.cr` is a **SharePoint** site. Each "Marco Legal" section page does not
expose plain `<a href>` PDF links; instead it embeds its document catalogue as
a **JSON blob** inside the page HTML, with PDF paths under
`/marco-legal/DocReglamento/`, `/DocNormativa/`,
`/DocAcuerdosJuntaDirectiva/`, and `/DocControlGacetario/` (forward slashes
escaped as `/`).

The scraper:

1. Fetches each section page and extracts every `/marco-legal/Doc*/*.pdf` path
   from the embedded JSON.
2. Downloads each PDF directly and extracts full text with `pdfplumber`.
3. Best-effort parses an issue date from the document body (long-form Spanish
   dates such as "27 de marzo de 2020").

## Usage

```bash
python bootstrap.py test                  # connectivity + extraction check
python bootstrap.py bootstrap --sample    # fetch 15 sample records
python bootstrap.py bootstrap --full      # fetch all documents
python bootstrap.py update                # re-discover (upsert dedup)
```

## Record schema

| Field          | Description                                              |
|----------------|----------------------------------------------------------|
| `_id`          | Live PDF URL (unique)                                    |
| `_source`      | `CR/BCCR-Regulations`                                    |
| `_type`        | `doctrine`                                               |
| `title`        | Document title (from filename)                           |
| `text`         | **Full text** extracted from the PDF                     |
| `date`         | Best-effort issue date (ISO, may be null)                |
| `category`     | reglamento / normativa / acuerdo_junta_directiva / ...   |
| `url`          | Live PDF URL                                             |
| `issuer`       | Banco Central de Costa Rica                              |
| `jurisdiction` | `CR`                                                     |
| `language`     | `es`                                                     |

## License

[Open Government Data (Costa Rica)](https://www.bccr.fi.cr/) — official
regulatory documents published by a Costa Rican public institution (Banco
Central de Costa Rica) for public use. Commercial use permitted (government
public-record material).
