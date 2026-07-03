# INTL/UEMOA-Legislation

UEMOA (Union Économique et Monétaire Ouest Africaine) legal instruments
from the e-docucenter portal at e-docucenter.uemoa.int.

Covers: Règlements, Directives, Décisions, Actes Additionnels, Protocoles
Additionnels of the West African Economic and Monetary Union.

8 member states: Benin, Burkina Faso, Côte d'Ivoire, Guinea-Bissau,
Mali, Niger, Senegal, Togo.

## Strategy

1. Fetch sitemap from e-docucenter.uemoa.int/fr/sitemap.xml
2. Filter URLs matching legal instrument patterns (règlement, directive, décision, etc.)
3. Scrape each page's `<article>` tag for full text (HTML, not PDF)
4. Parse instrument type and reference number from URL slug and title

## License

[UEMOA Official Publications](https://e-docucenter.uemoa.int/) — official legal instruments of an international organization, published for open public access. Attribution required.
