# SR/SRiS — Suriname Rechtsinformatie Systeem

Official legal information platform of the Foundation for the Rule of Law in Suriname (Stichting voor de Rechtsorde in Suriname). Publishes ~1,300+ PDF documents including legislation (Staatsblad), draft bills, Constitutional Court decisions, government decrees, and resolutions.

## Data Access

Uses the WordPress REST API media endpoint to enumerate all PDF documents, then downloads and extracts text from each.

- Endpoint: `https://www.sris.sr/wp-json/wp/v2/media?media_type=application`
- Format: PDF documents with text extraction via pypdf
- Coverage: Legislation from 1904 to present, Constitutional Court decisions (2021–2024)

## License

[Foundation for the Rule of Law in Suriname](https://www.sris.sr/) — official government legal texts published for public access. Government legislation is public domain under Suriname law.
