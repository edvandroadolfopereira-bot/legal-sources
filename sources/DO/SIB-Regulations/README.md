# DO/SIB-Regulations — Superintendencia de Bancos de la República Dominicana

Full-text regulatory and supervisory normative documents issued by the
**Superintendencia de Bancos de la República Dominicana (SB)**, the Dominican
banking supervisor.

## What this source collects

The "Normativas SB" archive on the supervisor's website collects the provisions
the Superintendent of Banks issues to the regulated financial system under the
authority of Article 21 of the Monetary and Financial Law (Ley núm. 183-02
Monetaria y Financiera):

- **Circulares** — supervisory circulars
- **Cartas Circulares** — circular letters
- **Circulares e Instructivos** — circulars adopting instructivos/manuals
- **Resoluciones SB** — supervisory resolutions

These cover regulatory reporting, accounting manuals, debida diligencia/AML,
credit information, and the operation and supervision of financial intermediation
entities. ~229 documents (a handful of the oldest are scanned images without
extractable text and are skipped).

Classified as **doctrine** — official regulatory guidance issued by a public
administrative authority.

## How it works

`sb.gob.do` is a custom CMS. The archive
`/regulacion/normativas-sb/?page=1&size=<N>` renders every document as a card
with its category, publication date, title, and subject. A single request with
a large page size returns the whole corpus. Each detail page links to one
`/media/<id>/<file>.pdf` containing the full text, which is downloaded and
extracted with `pdfplumber`.

## Usage

```bash
python bootstrap.py test               # Quick connectivity test
python bootstrap.py bootstrap --sample # Fetch 15 sample records
python bootstrap.py bootstrap          # Full pull
python bootstrap.py update             # Incremental update (by date)
```

## License

[Open Government Data (Dominican Republic)](https://sb.gob.do/regulacion/normativas-sb/) — official banking-supervision regulations published by a Dominican public institution (Superintendencia de Bancos) on its institutional website for public use. Attribution to the Superintendencia de Bancos is appropriate.
