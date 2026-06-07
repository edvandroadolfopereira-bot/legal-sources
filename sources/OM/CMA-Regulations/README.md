# OM/CMA-Regulations — Oman Capital Market Authority / Financial Services Authority

Full text of the laws, regulations and decisions governing Oman's **capital market
(securities)** and **insurance** sectors, published by the **Financial Services
Authority (FSA)** of Oman — the statutory regulator formerly known as the
**Capital Market Authority (CMA)** (renamed/merged into the FSA by Royal Decree
No. 20/2024).

## Data source

The FSA publishes the official enacted text of every instrument in its online
**Legislation Encyclopedia**:

- Portal: <https://e.fsa.gov.om/LegislationEncyclopedia/>

The public `cma.gov.om` / `fsa.gov.om` "DecisionsCirculars" listing pages currently
return HTTP 500, so this source instead uses the encyclopedia's structured back-end,
which is fully functional:

- **List** (POST, server-side DataTables JSON):
  `/LegislationEncyclopedia/GetPublishedLegislationList?type={Law|Regulation|Decision|Circular}`
  — returns `Id`, `LegislationNumberEn/Ar`, `HeaderEn/Ar`, `Type`, `Sector`, `IssueDate`.
- **Detail** (GET, HTML): `/LegislationEncyclopedia/DisplayLegislationDetails?id={id}&type={Type}`
  — full enacted text inside `<div id="content_{id}">`.

Sectors: `1` General, `2` Insurance, `3` Capital Market.

> Note: `e.fsa.gov.om` serves an incomplete TLS certificate chain, so the scraper
> disables certificate verification for this host.

## Coverage

~29 instruments (English text, Arabic metadata retained):

| Type | Count | `_type` |
|------|-------|---------|
| Law (Royal Decree) | 5 | legislation |
| Regulation | 12 | legislation |
| Decision | 12 | legislation |
| Circular | 0 | doctrine |

Examples: the Securities Law (RD 46/2022), Commercial Companies Law (RD 18/2019),
Takaful Insurance Law, the Acquisition & Takeover Regulation, and the Implementing
Regulation of the Capital Market Law. Documents range from ~14K to ~157K characters
of clean full text.

## Output schema

Each record contains: `_id`, `_source` (`OM/CMA-Regulations`), `_type`,
`_fetched_at`, `title`, `text` (full text), `date` (ISO 8601), `url`,
`legislation_type`, `legislation_number`, `sector`, `language`, and `title_ar`
where an Arabic header exists.

## Usage

```bash
python bootstrap.py test-api            # connectivity / record-count check
python bootstrap.py bootstrap --sample  # 15 sample records → sample/
python bootstrap.py bootstrap           # full pull
python bootstrap.py update              # incremental re-crawl
```

## License

Open Government Data — official legislation issued by the Government of Oman and
published by the Financial Services Authority. Government-issued laws, regulations
and decisions are public official texts, free to access and reuse with attribution.

[Financial Services Authority of Oman](https://fsa.gov.om/) — official publisher.
Commercial use permitted.
