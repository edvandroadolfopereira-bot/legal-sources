# INTL/BCEAO-Regulations

Regulatory texts issued by the **Banque Centrale des États de l'Afrique de l'Ouest (BCEAO)** — the central bank of the West African Economic and Monetary Union (UEMOA).

## Coverage

BCEAO regulations apply across the 8 UEMOA member states: Bénin (BJ), Burkina Faso (BF),
Côte d'Ivoire (CI), Guinée-Bissau (GW), Mali (ML), Niger (NE), Sénégal (SN) and Togo (TG).

Six regulatory domains are scraped from <https://www.bceao.int/fr/reglementations>:

- Textes régissant la politique monétaire
- Réglementation bancaire
- Réglementation des systèmes de paiement
- Réglementation des systèmes financiers décentralisés (microfinance / SFD)
- Réglementation des relations financières extérieures
- Lutte contre le blanchiment de capitaux et le financement du terrorisme (LBC/FT)

Document types: instructions, avis, décisions, circulaires, lois/règlements uniformes,
conventions and notes d'information.

## Access method

The site is a Drupal site whose category listing pages are server-rendered Views
(paginated via `?page=N`). Each row links to a regulation node alias under
`/fr/reglementations/…`. The individual node content is delivered client-side, but the
Drupal **node REST export** is available by appending `?_format=json` to any node alias,
which returns the title, date, document type and the attached PDF (`field_fichier.url`).
Full text is extracted from the PDFs.

No authentication is required.

## Usage

```bash
python bootstrap.py test
python bootstrap.py bootstrap --sample
python bootstrap.py bootstrap --full
```

## License

[Public domain (government)](https://www.bceao.int/) — official regulatory acts of the
BCEAO, a public regional institution. No usage restrictions are stated on the published
texts; commercial use permitted. Attribution to the BCEAO is courteous but not required.
