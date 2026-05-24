# CI/ConseilConstitutionnel — Conseil Constitutionnel de Côte d'Ivoire

Constitutional Council of Côte d'Ivoire — publishes decisions on constitutionality of laws, electoral disputes, and institutional matters.

- **URL:** https://www.conseil-constitutionnel.ci
- **Data type:** case_law
- **Coverage:** 1995–present (~570 decisions)
- **Language:** French
- **Format:** PDF (text-extractable via pdfplumber)

## Strategy

1. Paginate the decisions listing at `/decisions?page=N` (5 per page, ~114 pages)
2. Extract title and PDF URL from each `.views-row` card
3. Download PDF, extract full text with pdfplumber
4. Parse decision number and date from title

## License

[Public Domain (Government Work)](https://www.conseil-constitutionnel.ci) — official government constitutional decisions, public domain under Ivorian law.
