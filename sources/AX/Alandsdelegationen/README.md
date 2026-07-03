# AX/Alandsdelegationen — Åland Delegation Opinions (Ålandsdelegationens utlåtanden)

Ålandsdelegationen (the Åland Delegation) is the expert body established under
the Act on the Autonomy of Åland. Under § 56 of that Act it issues formal
opinions (*utlåtanden*) to the Finnish Council of State, the ministries, the
Government of Åland and the courts on the application of the Autonomy Act —
chiefly on the division of legislative and administrative competence between the
Republic of Finland and the autonomous province of Åland. Its review of every
Åland provincial law (*landskapslag*) is also the basis for the President of the
Republic's decision to confirm the law or let it lapse by veto.

These opinions are a unique, authoritative corpus of Åland constitutional /
competence-division law, published by the State Office of Åland (Statens
ämbetsverk på Åland).

## Source

- Case archive: https://www.ambetsverket.ax/alandsdelegationen/arenden
- Per-year pages: `/alandsdelegationen/arenden/{year}` (2007 onward)

## Method

- Iterate per-year case pages.
- **2025+**: each opinion is attached as a full-text PDF under
  `/sites/default/files/...` — downloaded and extracted via the shared
  `common.pdf_extract` backend.
- **2007–2024**: each opinion's full text is embedded inline as a `<li>` under
  `div.view-content` — extracted directly from the HTML.
- `normalize()` parses the case number (`Nr NN/YY`), signing date
  (`Helsingfors/Mariehamn DD.MM.YYYY`) and recipient (`Till …`) from the body.

Swedish language. `_type: doctrine`.

## Usage

```bash
python bootstrap.py test               # connectivity + first-PDF check
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap          # full run
```

## License

[Open Government Data — official documents of an authority](https://www.ambetsverket.ax/alandsdelegationen/arenden) — Under the Finnish Copyright Act § 9, decisions and statements of public authorities are excluded from copyright protection; Åland Delegation opinions are public records. No explicit open licence is stated on the site, so verify terms before commercial redistribution. Attribution to Statens ämbetsverk på Åland is appropriate.
