# PL/MonitorPolski — Monitor Polski (Polish Official Gazette)

Monitor Polski (*Dziennik Urzędowy Rzeczypospolitej Polskiej "Monitor Polski"*)
is Poland's second official journal. It publishes official state instruments
that are **not** generally-applicable statute law (those go in *Dziennik Ustaw*,
covered by [`PL/DziennikUrzedowy`](../DziennikUrzedowy/)):

- Resolutions of the Council of Ministers (*uchwały Rady Ministrów*)
- Orders of the Prime Minister and ministers (*zarządzenia*)
- Official announcements & consolidated-text notices (*obwieszczenia*)
- Resolutions of the Sejm and Senate
- Presidential decisions/orders (*postanowienia*), communiqués (*komunikaty*)

These are official, state-authored documents, classified here as **doctrine**.

## Data Access

Accessed via the official **Sejm ELI API** (`api.sejm.gov.pl`), publisher
code `MP` — the same well-documented API used for Dziennik Ustaw.

| Step | Endpoint |
|------|----------|
| List acts by year | `GET /eli/acts/MP/{year}` |
| Act metadata | `GET /eli/acts/MP/{year}/{pos}` |
| Full text (PDF) | `GET /eli/acts/MP/{year}/{pos}/text.pdf` |

Monitor Polski acts are published as **PDF only** (`textHTML=false`), so full
text is downloaded from the `/text.pdf` endpoint and extracted with **PyMuPDF
(fitz)**. Most acts extract cleanly; large multi-annex resolutions occasionally
contain tables rendered with subsetted custom fonts that extract imperfectly,
but the main body text is preserved.

## Usage

```bash
python bootstrap.py test-api               # connectivity + extraction test
python bootstrap.py bootstrap --sample     # 12 validation samples
python bootstrap.py bootstrap              # full pull
python bootstrap.py update                 # incremental (recent years)
```

## Coverage

- ~2001 onwards with consistent PDF text (~1,000+ acts/year in recent years).
- Default scrape window: 2015–2024 (configurable in `YEARS_TO_SCRAPE`).

## License

[Public Domain — Polish official documents](https://isap.sejm.gov.pl/) — no
attribution required.

Under **Art. 4 of the Polish Copyright Act** (*Ustawa o prawie autorskim i
prawach pokrewnych*), official documents, materials, marks and symbols are not
subject to copyright. Acts published in Monitor Polski are official documents in
the public domain; commercial use is permitted.
