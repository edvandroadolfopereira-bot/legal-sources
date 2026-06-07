# INTL/ISA-NatLeg — ISA National Legislation Database

National legislation from 50+ countries on deep seabed mining, compiled by the
International Seabed Authority (ISA). Documents are submitted by member states.

## Data Source

- **URL**: https://isa.org.jm/national-legislation-database/
- **Format**: PDF downloads from single listing page
- **Records**: ~112 documents
- **Languages**: Multiple (as submitted by member states)

## Strategy

1. Fetch the listing page and parse all PDF download links
2. Group by country using page structure (headings)
3. Download PDFs and extract text via pdfplumber
4. Normalize into standard LDH schema

## License

National legislation submitted by member states to ISA — publicly accessible.
