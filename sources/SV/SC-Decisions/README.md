# SV/SC-Decisions — Superintendencia de Competencia de El Salvador

Cases and resolutions of El Salvador's competition authority
(**Superintendencia de Competencia**, SC), pulled from the agency's public
"Casos en Línea" portal at <https://app.sc.gob.sv/>.

## What's captured

For every case the SC has handled (anticompetitive practices, economic
concentrations, infractions of the Ley de Competencia, etc.), the bootstrap
collects:

- **Case header** — title, economic agent investigated, market, alleged
  practice, sanction imposed, date opened.
- **Subject summary** — the official one-paragraph description of the case.
- **Full chronology of actuaciones** — every dated administrative or
  judicial event (Superintendente resolutions, Consejo Directivo decisions,
  appeals before the Sala de lo Contencioso Administrativo, Sala de lo
  Constitucional, Cámara de lo Contencioso Administrativo, etc.), with the
  acting body and a free-text description.
- **Underlying PDFs** — when the timeline event links to the official PDF
  ruling, the URL is preserved inline. The PDFs themselves are not
  downloaded (the page narrative is the captured legal text).

## Strategy

1. Scrape `https://app.sc.gob.sv/` for every `caso.php?id=<N>` link
   (~70 cases at the time of writing).
2. GET `caso.php?id=<N>` per case and parse:
   - `<title>` → case name
   - `<meta og:description>` → subject summary
   - Bold-label `<p>` pairs → Agente Económico, Práctica, Mercado, Sanción,
     Fecha de Apertura
   - `<div id="cr-cnt(lft|rght)">` blocks → timeline (date, actor,
     description, optional PDF URL)
3. Assemble `text` as a Markdown narrative: title, subject, metadata,
   chronologically-sorted event list.

## Running

```bash
python3 sources/SV/SC-Decisions/bootstrap.py test-api      # connectivity check
python3 sources/SV/SC-Decisions/bootstrap.py bootstrap --sample
python3 sources/SV/SC-Decisions/bootstrap.py bootstrap     # full sweep
```

Rate-limited to 1 request/second; a full sweep is ~1.5 minutes.

## Output schema

```json
{
  "_id": "sv-sc-<case_id>",
  "_source": "SV/SC-Decisions",
  "_type": "case_law",
  "_fetched_at": "2026-05-28T...",
  "title": "Caso HARISA",
  "text": "# Caso HARISA\n\nHARISA, S.A. DE C.V. cometió ...",
  "date": "2017-05-25",
  "url": "https://app.sc.gob.sv/caso.php?id=73",
  "case_id": 73,
  "economic_agent": "HARISA, S.A. de C.V.",
  "practice": "Acuerdos anticompetitivos entre competidores Art. 25 letra d)",
  "market": "Distribución de harina de trigo",
  "sanction": "$2,061,406.20",
  "opened_date": "2014-11-19",
  "event_count": 26,
  "language": "es",
  "country": "SV"
}
```

`date` is the most recent event in the timeline (i.e., the current state of
the case), falling back to the case-open date when no events are present.

## License

[Open Government Data — Ley de Acceso a la Información Pública](https://www.transparencia.gob.sv/institutions/sc) —
Resolutions and case histories published by El Salvador's
Superintendencia de Competencia on its public Casos en Línea portal as
part of its transparency obligations. No registration or paywall.
Attribution to the Superintendencia de Competencia is expected when
republishing.
