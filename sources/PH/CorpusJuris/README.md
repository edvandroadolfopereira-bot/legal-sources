# PH/CorpusJuris — Corpus Juris (Free Philippine Law Database)

Fetches Philippine legislation and Supreme Court jurisprudence from
[thecorpusjuris.com](https://thecorpusjuris.com/).

## Coverage

**Legislation:**
- Republic Acts (1946–present)
- Presidential Decrees (1972–1986)
- Acts of the Philippine Commission/Legislature (1900–1935)
- Batas Pambansa (1978–1986)
- Commonwealth Acts (1935–1946)

**Case Law:**
- Supreme Court decisions (1901–2020+), approximately 58,786 cases

## Strategy

1. Scrape index pages for each legislative category to discover document URLs
2. Scrape yearly/monthly jurisprudence index pages to discover case URLs
3. Fetch individual PHP pages and extract full text from article content
4. Clean HTML, normalize metadata

## License

[Public Domain (Government)](https://www.officialgazette.gov.ph/) — Philippine government works are in the public domain. The site states it is "always free" and will "never put data behind a paywall."
