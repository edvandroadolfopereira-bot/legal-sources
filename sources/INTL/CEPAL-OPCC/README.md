# INTL/CEPAL-OPCC — CEPAL Parliamentary Observatory on Climate Change

The **Parliamentary Observatory on Climate Change and Just Transition (OPCC)** is
a cooperation network led by CEPAL/ECLAC that tracks environmental legislation
across Latin America and the Caribbean.

## Data

- **2,900+ records**: environmental laws, climate change framework legislation, and bills
- **28 countries**: AR, BB, BZ, BO, BR, CL, CO, CR, CW, EC, GD, GT, GY, HN, LC, MS, MX, NI, PA, PE, PY, SR, SV, TC, TT, UY, VE, VG
- **Fields**: title, law number, date, status, topics, sectors, full text (from PDF)

## Access Method

1. **KoboToolbox API** at `api-kobo.cepal.org` returns all records as JSON (single request)
2. **PDF full text** downloaded from `geo.cepal.org/kbtx/` and extracted via pdfminer
3. Falls back to external legislation links when no PDF is available

## License

[CEPAL/ECLAC Legal Information](https://www.cepal.org/en/about/legal-information) — publicly available data with attribution required.
