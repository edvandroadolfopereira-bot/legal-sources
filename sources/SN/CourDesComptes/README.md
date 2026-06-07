# SN/CourDesComptes — Cour des Comptes du Sénégal

Audit reports, court decisions (arrêts), legal texts, and publications from Senegal's Court of Auditors.

## Data types

- **case_law**: Arrêts de la Cour (court decisions)
- **doctrine**: Rapports publics annuels, rapports sur l'exécution, rapports thématiques, rapports particuliers, legal texts, communiqués

## Strategy

WordPress REST API at `courdescomptes.sn/wp-json/wp/v2`:
- **Media API**: 268 PDF attachments downloaded and text extracted via pdfplumber
- **Posts API**: 201 posts with inline text (news, communiqués, legal texts)
- Category mapping for document classification

## License

[Public Government Documents (Senegal)](https://www.courdescomptes.sn/) — official audit reports and court decisions. Attribution required.
