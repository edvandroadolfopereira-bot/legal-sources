# INTL/Legislationline

OSCE/ODIHR Legislationline — Human Rights & Rule of Law Legislation Database.

Covers 57 OSCE participating states with legislation on human rights, rule of law,
elections, governance, and related topics. English translations and original language
texts available. ~14,000 documents total, ~7,000 with inline full text.

**Method:** Drupal JSON:API (`taxonomy_term/files` endpoint with pagination).

## Usage

```bash
python bootstrap.py test                  # Test connectivity
python bootstrap.py bootstrap --sample    # Fetch 15 sample records
python bootstrap.py bootstrap --full      # Full bootstrap (~14K docs)
```

## License

[OSCE/ODIHR Disclaimer](https://legislationline.org/disclaimer) — Legislation texts are generally public domain; OSCE commentary has no explicit license but is freely accessible. Attribution to OSCE/ODIHR recommended.
