# INTL/SCO-LegalDocs — Shanghai Cooperation Organisation Legal Documents

Official legal instruments of the Shanghai Cooperation Organisation (SCO),
published in English by the SCO Secretariat at `eng.sectsco.org`.

## Coverage

- **Founding instruments** — SCO Charter, Shanghai Convention on Combating
  Terrorism, Separatism and Extremism, RATS agreements
- **Declarations** — Samarkand, New Delhi, Moscow, Bishkek, Qingdao, Astana, etc.
- **Joint communiqués** — Heads of State and Heads of Government meetings
- **Statements** — on energy/food/supply-chain security, digital transformation,
  countering radicalization, climate, and other thematic areas
- **Decisions, memoranda and protocols** of SCO bodies

~117 documents (2001–present).

## Data source

The documents listing is paginated at `/documents/?offset={n}` (10 per page).
Each list item links to a detail page (`/YYYYMMDD/{id}.html`) carrying the
document metadata (date, type, event, place of signing, entry-into-force status)
and a **Download PDF** button. The full text lives in the PDF, which is
downloaded and extracted with `pdfplumber`. The detail-page metadata is captured
alongside the text (`doc_type`, `event`, `place_of_signing`, `status`, etc.).

Note: the same `/YYYYMMDD/{id}.html` URL pattern is reused by the site's
navigation menu, so the scraper only follows links carrying the
`list-item-document__link` class.

## License

[Open Government Data](https://eng.sectsco.org/documents/) — official SCO legal
instruments published by the Secretariat for public reference. The portal footer
asserts copyright on the website, but the underlying treaty, convention and
declaration texts are official intergovernmental instruments distributed for
public use.
