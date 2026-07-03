# PA/CENDOJ — Panama CENDOJ "Fallos de Interés"

Significant rulings ("fallos de interés") curated and published by the **Centro
de Documentación Judicial (CENDOJ)** of Panama's **Órgano Judicial**.

- **Listing:** https://www.organojudicial.gob.pa/cendoj/files/fallos-de-interes
- **Country / jurisdiction:** Panama (PA)
- **Data types:** `case_law` (individual rulings) and `doctrine` (jurisprudential
  digests — *extractos*, *recopilaciones*, *reseñas*)
- **Auth:** none

## What it collects

The collection spans **2009–2026** and includes:

- **Corte Suprema de Justicia — Pleno**: unconstitutionality demands
  (*demandas de inconstitucionalidad*), advisories (*advertencias*), and
  unconstitutionality rulings.
- **Sala Tercera de lo Contencioso Administrativo**: nullity / illegality
  decisions on administrative acts.
- **Habeas corpus / habeas data** decisions.
- **Jurisprudential digests** (DESCA extract, habeas-data recopilación, etc.).

## How it works

1. Paginates the server-rendered listing (`?page=N`) and parses each card's
   title, publication date, and PDF URL.
2. Downloads each ruling PDF from the static `/uploads/blogs.dir/` host.
3. Extracts the PDF text layer with **PyMuPDF (fitz)**.
4. Emits a normalized record **only when real full text is recovered** — a
   `chars-per-page` quality gate (≥150 chars/page, ≥2,000 chars total) skips the
   signed scans that have no text layer.

Of ~70 listed documents, ~29 are born-digital with full text (2K–310K chars
each); the rest are scanned images and are skipped.

```bash
python bootstrap.py test-api
python bootstrap.py bootstrap --sample      # ~15 full-text records into sample/
python bootstrap.py bootstrap               # full run into data/
```

## Bot manager note

The **HTML listing pages** are fronted by a **Radware Bot Manager**
(perfdrive / ShieldSquare hCaptcha) that serves a CAPTCHA page under sustained
or datacenter-IP traffic. The scraper warms a session against the homepage and
retries listing fetches with exponential backoff. The **ruling PDFs themselves
are static files and are not behind the bot wall**, so document download is
reliable once the listing has been read. From a flagged IP the listing fetch can
fail; in that case the run yields no records until the IP-level block clears.

## License

[Public Domain (government work)](https://www.organojudicial.gob.pa/) — decisions
of the Supreme Court of Justice of Panama are official acts of a government
authority, published by CENDOJ for public access. Treated as public-domain
government works; commercial use permitted, no attribution required.
