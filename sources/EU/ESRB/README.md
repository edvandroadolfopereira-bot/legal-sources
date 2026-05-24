# EU/ESRB — European Systemic Risk Board

Recommendations, warnings, opinions and decisions of the European Systemic Risk Board (ESRB), the EU body responsible for macro-prudential oversight of the financial system.

## Data Access

Uses the EU Publications Office CELLAR SPARQL endpoint to discover documents authored by ESRB, then fetches full text via CELLAR content negotiation (HTML/XHTML).

- SPARQL endpoint: `http://publications.europa.eu/webapi/rdf/sparql`
- Full text: `http://publications.europa.eu/resource/celex/{CELEX}` with HTML Accept header

## Coverage

~234 documents from 2011 to present, including:
- Recommendations (macroprudential policy measures)
- Warnings (systemic risk alerts)
- Opinions (legislative consultations)
- Decisions (internal governance)

## License

[EUR-Lex legal notice](https://eur-lex.europa.eu/content/legal-notice/legal-notice.html) — reuse permitted with attribution to the European Union.
