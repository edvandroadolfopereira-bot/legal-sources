# LB/ParliamentLaws — Lebanese Parliament Approved Laws

Laws approved by the Lebanese Parliament (مجلس النواب اللبناني), spanning from 1994 to present.

## Data Source

- **Website**: https://www.lp.gov.lb
- **Endpoint**: ASP.NET ASMX web services at `/Webservice.asmx`
- **Coverage**: ~500+ laws across 27 legislative years (1994–2026)
- **Language**: Arabic
- **Format**: PDF (base64-encoded, served via API)

## API Endpoints

| Endpoint | Method | Params | Returns |
|----------|--------|--------|---------|
| `GetLawsByYear` | POST | `pageNumber` | Array of year strings |
| `GetLawSectionNumber` | POST | `Year` | Integer count |
| `GetLawsBySection` | POST | `pageNumber`, `Year` | Array of section name strings |
| `GetLawNumber` | POST | `Section` | Integer count |
| `GetLaws` | POST | `pageNumber`, `Section` | Array of law objects |
| `GetLawFile` | POST | `ID` | `{base64, fileName}` |

All endpoints use `Content-Type: application/x-www-form-urlencoded` with `X-Requested-With: XMLHttpRequest`.

## License

[Public Domain (Government Works)](https://www.lp.gov.lb) — Official parliamentary legislation published by the Lebanese state.
