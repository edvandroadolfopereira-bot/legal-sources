# MZ/BM-Regulations — Banco de Moçambique

Regulatory notices (avisos), circulars, decrees, and instructions from
Banco de Moçambique, the central bank of Mozambique.

~311 documents covering banking supervision, monetary policy, payment
systems, and financial sector regulation.

## Strategy

1. Scrape paginated listing at `/pt/o-banco/normativos/` (5 docs/page, ~63 pages)
2. Extract PDF URL, title, and date from each listing entry
3. Download each PDF and extract full text with PyMuPDF (fitz)
4. Normalize into standard records

## License

[Public Domain (Government of Mozambique)](https://www.bancomoc.mz/pt/informacao-legal/) — official central bank regulations published for public access.
