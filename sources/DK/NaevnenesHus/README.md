# DK/NaevnenesHus — Denmark Centralized Tribunal Portal

Decisions from 14 Danish administrative tribunals hosted by [Naevnenes Hus](https://naevneneshus.dk/).

## Tribunals covered

| Subdomain | Tribunal | Approx. decisions |
|-----------|----------|-------------------|
| pkn | Planklagenaevnet (Planning Appeals) | ~13,000 |
| mfkn | Miljo- og Fodevareklagenaevnet (Environment & Food) | ~21,700 |
| dkbb | Disciplinaer- og klagenaevnet for beskikkede bygningssagkyndige | ~4,400 |
| ekn | Energiklagenaevnet (Energy Appeals) | ~2,760 |
| byg | Byggeklageenheden (Building Complaints) | ~1,990 |
| klfu | Klagenaevnet for Udbud (Public Procurement) | ~1,690 |
| apv | Ankenaevnet for Patenter og Varemaerker (Patents & Trademarks) | ~1,575 |
| rn | Revisornaevnet (Auditor Tribunal) | ~1,290 |
| ean | Erhvervsankenaevnet (Commercial Appeals) | ~1,150 |
| fkn | Forbrugerklagenaevnet (Consumer Complaints) | ~750 |
| dnfe | Disciplinaernaevnet for Ejendomsmaglere (Real Estate Agents) | ~620 |
| tvist | Tvistighedsnaevnet (Apprenticeship Disputes) | ~210 |
| tele | Teleklagenaevnet (Telecom) | ~206 |
| byf | Byfornyelsesnaevnene (Urban Renewal) | ~140 |

**Total: ~51,500 decisions**

## Data access

Each tribunal runs an Angular SPA backed by a .NET Core REST API at `https://{subdomain}.naevneneshus.dk/api/search`. The search endpoint returns full decision text (HTML) in the `body` field. No authentication required.

## License

[Public Domain (Danish Government)](https://naevneneshus.dk/) — Danish administrative tribunal decisions are public documents.
