# BB/FTC-Decisions — Barbados Fair Trading Commission Decisions

Full text of decisions, orders, and merger determinations issued by the
**Barbados Fair Trading Commission (FTC)**, the statutory body responsible for
utility regulation, competition enforcement, and consumer protection in Barbados.

## What this source covers

- **Utility rate decisions** — Cable & Wireless (Barbados) / FLOW, Barbados
  Light & Power Company, Barbados Water Authority rate reviews.
- **Price Cap Plans** — periodic price-cap determinations for telecoms.
- **Feed-in-tariff (FIT) decisions** — renewable energy tariff orders.
- **Standards of Service (SOS)** decisions and orders for regulated utilities.
- **Interconnection / RIO** decisions and dispute resolutions.
- **Merger determinations** under the Fair Competition Act (CAP. 326C).
- **Commission orders** and procedural orders.

Documents span **2002 to the present** (latest captured: 2025).

## Data access

The FTC website (`ftc.gov.bb`) runs on Joomla and is **frequently placed in
"offline for maintenance" mode**, which returns an offline page for every
`index.php` request. However, the underlying web server **still serves the
static decision PDFs** stored under `/library/` directly.

The scraper therefore:

1. **Enumerates** decision PDF URLs from the **Wayback Machine CDX index**
   (`web.archive.org/cdx`), a stable public listing of every `/library/*.pdf`
   the FTC has ever published.
2. **Filters** to genuine Commission decisions / orders / determinations
   (excluding forms, guidelines, party motions, speeches, and brochures).
3. **Downloads each PDF from the LIVE site** (`www.ftc.gov.bb/library/...`)
   and extracts full text with `pdfplumber`.

Older scanned PDFs (mostly pre-2004) that lack an extractable text layer are
skipped automatically.

## Usage

```bash
python bootstrap.py test                  # connectivity + extraction check
python bootstrap.py bootstrap --sample    # fetch 15 sample records
python bootstrap.py bootstrap --full      # fetch all decisions
python bootstrap.py update                # incremental (by issue date)
```

## Record schema

| Field        | Description                                   |
|--------------|-----------------------------------------------|
| `_id`        | Live PDF URL (unique)                         |
| `_source`    | `BB/FTC-Decisions`                            |
| `_type`      | `case_law`                                    |
| `title`      | Decision title (from filename)                |
| `text`       | **Full text** extracted from the PDF          |
| `date`       | Issue date (ISO `YYYY-MM-DD`, from filename)  |
| `url`        | Live PDF URL                                  |
| `court`      | Barbados Fair Trading Commission              |
| `jurisdiction` | `BB`                                        |

## License

[Open Government Data (Barbados)](https://www.ftc.gov.bb/) — official
regulatory decisions published by a Barbados statutory body for public use.
Attribution to the Barbados Fair Trading Commission is appreciated.
Commercial use permitted (government public-record material).
