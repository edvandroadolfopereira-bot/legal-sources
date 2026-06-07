# UG/IndustrialCourt — Industrial Court of Uganda

Labour court awards, rulings, and judgements from Uganda's Industrial Court.

## Data types

- **case_law**: Awards, rulings, judgements in labour and employment disputes

## Strategy

WordPress REST API at `industrialcourt.go.ug/wp-json/wp/v2`:
- **Media API**: ~564 attachments — filter PDFs whose titles contain
  `RULING`, `AWARD`, `JUDGEMENT`, or `JUDGMENT`; skip cause lists
- Text extracted via pdfplumber

## License

[Public Government Documents (Uganda)](https://industrialcourt.go.ug/) — official court rulings from a government court. Public record. Attribution recommended.
