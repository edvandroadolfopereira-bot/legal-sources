# IT/Sicilia — Leggi della Regione Siciliana

Regional laws (*leggi regionali*) of the Sicilian Region, published by the
**Assemblea Regionale Siciliana (ARS)** in its *Banche Dati*.

- **Jurisdiction:** Sicily (ISO 3166-2: `IT-82`)
- **Publisher:** Assemblea Regionale Siciliana — https://www.ars.sicilia.it
- **Search front-end:** https://w3.ars.sicilia.it/home/cerca/201.jsp
- **Coverage:** I Legislatura (1947) → present
- **Data type:** legislation

## Access method

The ARS search front-end (`/home/cerca/201.jsp`) drives a stateful ICA/Tomcat
search engine under `/icaro/` whose result listing is rendered through browser
JavaScript (a popup window calling `/icaro/default.jsp` + `/icaro/shortList.jsp`),
which is impractical to consume server-side.

Fortunately, every law is **also** published as a single consolidated HTML
document under a stable, enumerable URL scheme:

```
https://w3.ars.sicilia.it/lex/L_{YEAR}_{NUMBER:03d}.htm
```

e.g. `/lex/L_1947_001.htm`, `/lex/L_2025_001.htm`.

`bootstrap.py` enumerates year-by-year (1947 → current). For each year it
increments the law number from 1 until it hits several consecutive HTTP 404s
(laws are numbered consecutively from 1 each year). Each document is decoded
from windows-1252 and its full text (all articles), title, promulgation date,
*Legislatura*, and *G.U.R.S.* reference are extracted.

## Sample

`python bootstrap.py bootstrap --sample` saves 15 records to `sample/`. Each
record contains the full text of the law (header + every `ARTICOLO`).

## License

[Public domain — official acts, Art. 5 L. 633/1941](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633!vig=) — no attribution required.

Regional laws are official acts of a public administration and, under Article 5
of the Italian Copyright Law (*Legge 22 aprile 1941, n. 633*), are not protected
by copyright. Commercial use is permitted.
