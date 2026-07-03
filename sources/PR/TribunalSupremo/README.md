# PR/TribunalSupremo — Puerto Rico Supreme Court Opinions

Full-text opinions and resolutions of the **Supreme Court of Puerto Rico**
(*Tribunal Supremo de Puerto Rico*), published officially by the Rama Judicial
de Puerto Rico at [dts.poderjudicial.pr](https://dts.poderjudicial.pr/opiniones/).

## Data

- **Type:** case_law
- **Language:** Spanish
- **Coverage:** ~150–250 opinions per year, archived from 1998 onward
- **Format:** Full-text PDF per opinion, cited as `YYYY TSPR NNN`
- **Auth:** None

## How it works

`bootstrap.py` iterates the official year index pages
(`/opiniones/{YEAR}/{YEAR}.htm`), collects every opinion PDF link (resolving
both the newer absolute `/ts/{year}/{year}tsprNNN.pdf` scheme and the older
relative `{year}TSPRNNN.pdf` scheme), downloads each PDF, and extracts the full
text with `pdfplumber` (PyMuPDF fallback). Citation, case number, decision date,
and party caption are parsed from the consistent PDF header
("EN EL TRIBUNAL SUPREMO DE PUERTO RICO" … "Número del Caso:" … "Fecha:").

```bash
python bootstrap.py test                  # connectivity test
python bootstrap.py bootstrap --sample     # 15 sample records -> sample/
python bootstrap.py bootstrap-fast --full  # full pull -> data/records.jsonl
python bootstrap.py update                 # current-year opinions
```

## License

[Public domain (US government)](https://www.law.cornell.edu/uscode/text/17/105) — Puerto Rico court opinions are works of the government in the public domain; no attribution required, commercial use permitted.
