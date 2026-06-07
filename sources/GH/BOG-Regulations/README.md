# GH/BOG-Regulations — Bank of Ghana Regulations & Directives

Bank of Ghana regulatory documents including banking regulations, directives,
guidelines, and banking acts. Documents are published as PDFs on the BOG
WordPress site.

## Data Access

Documents are discovered via the WordPress REST API custom post types:
- `reg_directives` — 61 regulations and directives
- `banking_acts` — 5 banking acts

Each post's PDF attachment is fetched via the `wp:attachment` link, downloaded,
and text-extracted using pdfminer.

## License

[Bank of Ghana Disclaimer](https://www.bog.gov.gh/disclaimer/) — official regulatory documents published for public access. No explicit restriction on reuse.
