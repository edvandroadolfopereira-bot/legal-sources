# INTL/IFC-CAO — IFC/MIGA Compliance Advisor Ombudsman Cases

Cases from the Compliance Advisor Ombudsman (CAO), the independent accountability mechanism of the International Finance Corporation (IFC) and Multilateral Investment Guarantee Agency (MIGA), World Bank Group.

- **Source**: https://www.cao-ombudsman.org/cases
- **Type**: case_law
- **Coverage**: ~250+ complaints since 2000
- **Content**: Assessment reports, compliance investigation reports, dispute resolution documents
- **Full text**: Extracted from PDF reports using PyMuPDF

## How it works

1. CSV export at `/export-all-cases` provides case metadata index
2. Sitemap provides ~84 case page URLs (Drupal CMS with `http://default/` base URL quirk)
3. Each case page links to PDF documents (assessment reports, investigation reports, etc.)
4. Best English-language PDF is selected and text extracted via PyMuPDF

## License

[World Bank Group Open Access](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) — CAO reports and decisions are published for public accountability. Attribution required.
