# INTL/WTO-Disputes

Full text of **modern WTO dispute settlement reports** (DS1–present, 1995–onwards):
adopted panel reports, Appellate Body reports, compliance (Art. 21.5) reports and
arbitration awards.

Distinct from `INTL/GATT-Disputes`, which covers the GATT 1947 era (1948–1995).

## Access

No authentication. All data comes from public WTO endpoints:

1. **Document listing** — WTO Documents Online XML API:
   ```
   https://docs.wto.org/dol2fe/Pages/SS/GetXMLResults.aspx
     ?DataSource=Cat&query=@Symbol=WT/DS{N}/*&Language=English
   ```
   Returns `<DOCUMENT>` records with `SYMBOL`, `CATID`, `FILENAMESA` (file path),
   `RESTRICTIONTYPENAME` (`U`=unrestricted, `D`=de-restricted, `R`=restricted) and
   `ISSUINGDATE`.

2. **Report identification** — by symbol suffix:
   | Symbol | Document |
   |--------|----------|
   | `WT/DS{N}/R` | Panel report |
   | `WT/DS{N}/AB/R` | Appellate Body report |
   | `WT/DS{N}/RW[n]` | Compliance (Art. 21.5) panel report |
   | `WT/DS{N}/AB/RW[n]` | Compliance Appellate Body report |
   | `WT/DS{N}/ARB[..]` | Arbitration award (Art. 22.6 / 25) |

   Only `U`/`D` (publicly available) reports are fetched; member-restricted (`R`)
   documents are skipped.

3. **Full text** — each report PDF is downloaded from:
   ```
   https://docs.wto.org/dol2fe/Pages/FE_Search/ExportFile.aspx
     ?Id={CATID}&filename={path}&Open=True
   ```
   and extracted with `pdfplumber`.

4. **Narrative summary** — the Secretariat's "Summary of the dispute to date" and the
   dispute title are scraped from the per-case page
   (`/english/tratop_e/dispu_e/cases_e/ds{N}_e.htm`) and prepended to the report text.

Only disputes that reached at least one publicly-available report are emitted —
consultation-only / settled disputes have no adjudicative full text.

## Usage

```bash
python bootstrap.py test               # connectivity check (DS8)
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap          # all disputes (sequential)
python bootstrap.py bootstrap-fast     # concurrent full run
```

Requires `pdfplumber` for PDF text extraction.

## Output schema

`_id`, `_source`, `_type` (`case_law`), `title`, `text` (full report text),
`date` (latest report date), `url`, `dispute_number`, `report_symbols`,
`report_count`.

## License

> ⚠️ **Commercial use restricted.** WTO documents are publicly available, but
> reproduction for commercial purposes requires WTO permission.

[WTO Copyright / Terms of Use](https://www.wto.org/english/res_e/booksp_e/terms_of_use_e.htm)
— attribution required; non-commercial reproduction permitted.
