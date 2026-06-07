# PE/JNE — Peru Jurado Nacional de Elecciones

Resolutions and jurisprudence from Peru's National Elections Jury (JNE).

## Coverage

- Electoral disputes (vacancia, suspensión, nulidad electoral)
- Propaganda and publicity rulings
- Inscription of candidate lists
- Electoral acts and results proclamation
- Control ciudadano, derechos de participación
- Years: 2014–2026 (as available in the jurisprudencia system)

## Data access

Uses the internal JSON API behind the AngularJS frontend at
`jurisprudencia.jne.gob.pe`. Key endpoints:

- `/Home/InicioJurisprudencia` — list of case types and years
- `/Generales/GeneraConsultaRapida` — set search criteria in session
- `/Resoluciones/ConsultarResoluciones` — fetch matching resolutions

Full text is returned in the `strParteResolutiva` field of each resolution.
PDFs are available at `/Tmp/Proyectos/{idProyecto}.pdf` for most records.

## License

[Government of Peru — Open Access](https://www.gob.pe/institucion/jne/informes-publicaciones) — public electoral jurisprudence published for transparency. Attribution required.
