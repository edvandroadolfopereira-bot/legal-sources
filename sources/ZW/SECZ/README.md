# ZW/SECZ — Securities and Exchange Commission of Zimbabwe

Regulatory doctrine from Zimbabwe's securities and capital markets regulator.

**URL:** https://seczim.co.zw/
**Data type:** doctrine
**Format:** WordPress REST API + PDF extraction

## What's collected

- Regulatory directives and notices
- AML/CFT guidance
- Market guidelines
- Publications and newsletters
- Enforcement decisions

## Strategy

1. **WP Media API** (`/wp-json/wp/v2/media?media_type=application`): ~479 PDF
   attachments downloaded and text extracted via pdfplumber.
2. **WP Posts API** (`/wp-json/wp/v2/posts`): ~604 posts. Posts with substantial
   inline text (>200 chars after HTML stripping) are included as separate records.

## License

[Public Government Documents](https://seczim.co.zw/) — official regulatory
publications from the Securities and Exchange Commission of Zimbabwe. No explicit
open data license published; documents are public regulatory notices intended
for market participants.
