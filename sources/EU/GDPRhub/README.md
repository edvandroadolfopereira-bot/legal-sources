# EU/GDPRhub — European DPA Decisions Wiki

GDPR enforcement decision database maintained by noyb.eu (Max Schrems' organisation).
Collects Data Protection Authority decisions from 30+ European countries with English
summaries and machine translations.

- **Coverage**: 3,200+ DPA enforcement actions across EU/EEA
- **Data types**: case_law (DPA decisions), doctrine (guidelines)
- **Languages**: English summaries; original decisions in national languages
- **API**: MediaWiki API (`api.php`) — no authentication required
- **Update frequency**: Continuous (wiki edits)

## Data Access

Uses the MediaWiki `embeddedin` API to enumerate all pages using the
`DPAdecisionBOX` template, then batch-fetches wikitext content. Structured
metadata is parsed from template parameters; full text from English Summary
and Machine Translation sections.

## License

[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — attribution and share-alike required.
