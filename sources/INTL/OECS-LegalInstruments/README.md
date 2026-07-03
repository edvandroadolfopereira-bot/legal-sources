# INTL/OECS-LegalInstruments

OECS Authority communiqués, statements, declarations, and legal instruments from
the Organisation of Eastern Caribbean States.

## Data sources

1. **Authority Communiqués** (64th–77th+ meetings): Official OECS Authority
   meeting communiqués with binding decisions. Full HTML text via Prezly JSON
   API at `pressroom.oecs.int`.
2. **Special/Emergency Meetings**: Communiqués from special and emergency
   sessions of the OECS Authority.
3. **ECCB Monetary Council Communiqués**: Decisions of the Eastern Caribbean
   Central Bank Monetary Council.
4. **Statements & Declarations**: OECS Authority statements on regional matters.
5. **Legal Library PDFs** (optional): Revised Treaty of Basseterre and other
   legal documents, extracted via pdfplumber when available.

## Strategy

- Parse `pressroom.oecs.int/sitemap.xml` for legal content URLs
- Fetch each via Prezly JSON endpoint (`.json` suffix) for structured full text
- Strip HTML from body field for clean text
- Optionally download Treaty and legal library PDFs (requires pdfplumber)

## License

[OECS Official Publications](https://oecs.int/) — official legal instruments
published for public access. Attribution required.
