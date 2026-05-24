# INTL/UEMOACourt — UEMOA Court of Justice Decisions

Fetches decisions from the **Cour de Justice de l'Union Économique et Monétaire Ouest Africaine (UEMOA)** — the Court of Justice of the West African Economic and Monetary Union.

## Data Source

- **Website**: https://courdejusticeuemoa.org
- **Method**: WordPress AJAX API (admin-ajax.php) + PDF text extraction
- **Coverage**: ~86 decisions (58 arrêts, 19 avis, 9 ordonnances)
- **Language**: French
- **Member States**: Benin, Burkina Faso, Côte d'Ivoire, Guinea-Bissau, Mali, Niger, Senegal, Togo

## Document Types

| Type | French | Count | API Action |
|------|--------|-------|------------|
| Judgments | Arrêts | ~58 | `search_arret_files` |
| Advisory Opinions | Avis | ~19 | `search_avis_files` |
| Orders | Ordonnances | ~9 | `search_ordonnance_files` |

## Usage

```bash
python bootstrap.py test               # Connectivity test
python bootstrap.py bootstrap --sample # Fetch 15 sample records
python bootstrap.py bootstrap          # Fetch all records
```

## License

[Public Domain (Government Judicial Decisions)](https://courdejusticeuemoa.org) — Official judicial decisions of an international court are public domain under general principles of international law.
