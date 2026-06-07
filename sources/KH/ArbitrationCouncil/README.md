# KH/ArbitrationCouncil — Arbitration Council of Cambodia (Labor Decisions)

The **Arbitration Council** is Cambodia's tripartite quasi-judicial body for
resolving collective labor disputes, established in 2003 under the 1997 Labour
Law (Article 309 et seq.) and Prakas No. 099 MOSALVY. It issues **arbitral
awards** that are published openly on its website. This source collects those
awards as `case_law`.

- **Country:** KH (Cambodia)
- **Type:** case_law (arbitral awards on collective labor disputes)
- **Coverage:** ~1,940 awards, 2004–present
- **Languages:** Khmer and (for many awards) English
- **Auth:** none

## Access

Awards are served through the WordPress Download Manager (`wpdm`) plugin:

1. The listing page
   `https://www.arbitrationcouncil.org/arbitral-decision/arbitral-award/?wpdmc=arbitral-awards`
   enumerates every award as a `/download/{slug}/` link (a single page lists all
   ~1,940 awards).
2. Each award page `/download/{slug}/` exposes one or more download buttons of
   the form `/download/{slug}/?wpdmdl={id}&refresh={token}`. The `refresh` token
   is generated per page load; the PDF is fetched from that URL with a `Referer`
   header set to the award page.
3. Full text is extracted from the PDF with PyMuPDF (fallback: pdfminer).

### Full-text caveat

Older awards (≈2004–2016), especially the **English** versions, are
born-digital PDFs with a real text layer and extract cleanly (15K–50K chars).
Many later awards and Khmer-only versions are **scanned images** with no text
layer. Records whose extracted text is below `MIN_TEXT_CHARS` (400) are skipped,
so the dataset contains only awards with usable full text.

## Files

- `config.yaml` — source configuration and schema
- `bootstrap.py` — fetcher (`fetch_all`, `fetch_updates`, `normalize`)
- `sample/` — validation samples (12 awards with full text)

## Usage

```bash
python bootstrap.py test-api                 # connectivity check
python bootstrap.py bootstrap --sample       # sample run (12 records)
python bootstrap.py bootstrap                 # full bootstrap
python bootstrap.py update                    # incremental (append-only)
```

## License

> ⚠️ **Commercial use restricted.** The arbitral awards are official
> quasi-judicial decisions (public legal records), but the publisher's website
> asserts blanket copyright with no open license. Treat commercial reuse as
> restricted until clarified with the Arbitration Council.

[Arbitration Council — site terms](https://www.arbitrationcouncil.org/) —
the site footer states *"Copyright © The Arbitration Council. All rights
reserved."* No explicit open-data or Creative Commons license is published.
Attribution to the Arbitration Council of Cambodia is expected.
