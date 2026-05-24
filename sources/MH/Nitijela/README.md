# MH/Nitijela — Marshall Islands Parliament (Nitijela) Legislation

Acts of the Nitijela (Parliament of the Marshall Islands), sourced from the
official RMI Parliament website. Includes principal acts (1966–present),
subordinate regulations, and amending legislation.

- **Source**: https://rmiparliament.org/cms/legislation.html
- **Format**: PDF (digitally created, text-selectable)
- **Coverage**: ~305 principal acts, 1966–2025
- **Language**: English
- **Data type**: legislation

## How it works

1. Fetches the "Acts by Title" listing page (all acts on one page)
2. Parses the HTML table for act metadata (title, legislation number, date, PDF URL)
3. Downloads each act's PDF and extracts full text using pypdf
4. Normalizes into standard schema with full text

## License

> ⚠️ **Commercial use restricted.** See terms below.

[Custom Terms](https://rmiparliament.org/cms/legislation.html) — "Legislation can be downloaded and printed for private use. Any commercial entity is required to obtain permission to reuse the data from the Marshall Islands Attorney General's Chambers."
