# Israel Knesset Data (Hasadna Open Source)

**Source:** [production.oknesset.org/pipelines/data/laws/](https://production.oknesset.org/pipelines/data/laws/)
**Country:** IL
**Data types:** legislation
**Status:** Complete

Israeli legislation from the Hasadna Open Knesset data pipeline. Joins the
`kns_law` table (60,651 law records) with `kns_document_law` (9,642 PDF links)
to download official gazette publications from `fs.knesset.gov.il`. Full text
extracted from PDFs via pdfplumber.

Coverage: ~4,042 laws with associated PDF documents. Official gazette
publications ("חוק - פרסום ברשומות") are preferred when multiple documents exist.

## License

[Open Knesset — Hasadna (MIT tools, Israeli government open data)](https://github.com/hasadna/knesset-data) — Israeli government parliamentary data made available through Hasadna's open-source pipeline. Attribution to Hasadna/Open Knesset required.
