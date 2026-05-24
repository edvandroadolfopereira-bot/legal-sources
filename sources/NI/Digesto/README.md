# NI/Digesto — Digesto Juridico Nicaraguense

Nicaragua's consolidated legal database maintained by the National Assembly.
41,000+ norms including laws, decrees, executive agreements, codes, and
international instruments from 1821 to present.

## Data Access

- **API**: POST to `/consultas/util/ws/proxy.php`
- **Listing**: `hddQueryType=getJuridicNorms` with pagination (100/page)
- **Full text**: `hddQueryType=getNormaHtmlAccordion` with base64-encoded ID
- **Fallback**: `loadVersionsXML` + `getVersionHtmlAccordion` for versioned norms
- **Auth**: None required

## Coverage

- ~41,460 norms total
- ~60% have accessible full text (laws have near 100% coverage)
- Types: Ley, Decreto, Codigo, Acuerdo, Reglamento, Resolucion, etc.

## License

[Public domain (government)](http://digesto.asamblea.gob.ni/) — official Nicaraguan legislation published by the National Assembly for public access. No explicit license stated; government-produced legal texts are public domain under Nicaraguan law.
