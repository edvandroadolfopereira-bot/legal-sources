# FR/OrdreMedecins — Ordre des Médecins Disciplinary Jurisprudence

Disciplinary decisions from the French National Medical Order (*Ordre national des médecins*), covering:
- **Chambre disciplinaire nationale** (national appeal chamber)
- **Chambres disciplinaires de première instance** (regional first-instance chambers)

Source: https://www.jurisprudence.ordre.medecin.fr/

## Data

- ~20,000+ anonymized disciplinary decisions
- Full text extracted from official PDF exports
- Metadata: jurisdiction, dossier number, date, keywords, abstract, CSP articles cited
- Covers sanctions for medical misconduct, deontological violations, professional obligations

## Technical Notes

The site uses a Struts 2 framework with server-side conversation state. Each decision is accessed via `FicheDetailConsultation.do?ficId=N`. Full text is obtained by:
1. Loading the detail page (GET) to obtain the CTX conversation token
2. POSTing back with the CTX token to trigger the "Exporter la décision" PDF download
3. Extracting text from the PDF using pdfplumber

A fresh HTTP session is required for each decision (Struts 2 CTX tokens conflict across pages in a shared session).

## License

[Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) — French public sector disciplinary decisions, open data under Loi pour une République Numérique. Attribution required.
