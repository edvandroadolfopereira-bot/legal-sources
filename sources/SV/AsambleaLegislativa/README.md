# El Salvador Legislative Assembly — Leyes y Decretos

**Source:** [https://www.asamblea.gob.sv/leyes-y-decretos/busqueda-decretos](https://www.asamblea.gob.sv/leyes-y-decretos/busqueda-decretos)
**Country:** SV
**Data types:** legislation
**Status:** Complete

## Overview

Official database of laws and legislative decrees published by the Asamblea
Legislativa de la República de El Salvador. Decrees are organized by year (1860s
to present). Each decree links to the official PDF carrying the full text.
Language: Spanish.

## Access strategy

No public API. The fetcher uses the structured Drupal HTML index plus per-document
PDFs:

1. `/leyes-y-decretos/decretos-por-anios` lists every year with decrees;
   `/leyes-y-decretos/decretos-por-anios/{year}/0` lists all decree cards for a year.
2. Each card links to a node page `/leyes-y-decretos/view/{id}` carrying structured
   metadata (decree number, dates, materia, rama del derecho, resumen) and the
   official PDF link.
3. The PDF holds the **full text**. Recent decrees are digital-native (extractable
   text), extracted with `pdfplumber`.

Older scanned-image decrees that yield fewer than 400 extractable characters are
skipped — this source only contributes full-text records.

## License

[Open Government Data](https://www.asamblea.gob.sv/) — legislation produced by the
State of El Salvador is public. The Asamblea Legislativa publishes official texts
openly without registration. No explicit machine-readable license is stated;
treated as open government data (public-domain legal texts). Commercial use OK.
