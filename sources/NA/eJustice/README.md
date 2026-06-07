# NA/eJustice — Namibia eJustice Portal

Court judgments of the High Court and Supreme Court of Namibia, published on
the official eJustice SharePoint portal.

- **Source**: https://ejustice.jud.na
- **Data type**: Case law
- **Language**: English
- **Coverage**: High Court (Civil, Criminal, Labour, Tax) and Supreme Court
- **Method**: SharePoint folder browse listings + python-docx text extraction

## How it works

The eJustice portal is a SharePoint site whose judgment libraries are exposed
through folder URLs (e.g. `/High Court/Judgments/Civil/`). A GET on a folder
returns an HTML directory listing that contains every `.docx` link. The scraper
extracts those links, downloads each Word document, and pulls the text from
both paragraphs and tables (the SharePoint template puts the case header in a
table, so plain paragraph extraction would miss most of the content).

The filename embeds parties, the case number, the neutral citation
(e.g. `[2025] NAHCMD 21`), and the date, which are parsed via regex.

## License

[Public Domain (Government)](https://ejustice.jud.na) — Official judgments of
Namibian courts are public domain. The site carries no terms restricting reuse
of judgments themselves.
