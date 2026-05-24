# KG/CourtActs — Kyrgyzstan Judicial Acts Database (All Courts)

State Registry of Judicial Acts (GRSA) via the Digital Justice Portal at [portal.sot.kg](https://portal.sot.kg).

Covers **all 73 Kyrgyz courts**: Supreme Court, 8 regional/oblast courts, 7 administrative courts, city courts, and 40+ district courts. Over 213,000 cases with published judicial acts since 2013. Case types include civil, criminal, administrative, economic, and constitutional matters.

Data is anonymized (depersonified) and available in Kyrgyz and Russian.

This source is broader than KG/SupremeCourt, which only covers court_id=87.

## Access

- **API**: `https://portal.sot.kg/api/v1/cc_court_case/?case_act_exist=true`
- **Auth**: None required
- **Format**: JSON with inline HTML full text in `case_act[].file_html`
- **Pagination**: Page-based (`page` + `per_page` params)

## License

[Public Domain](https://portal.sot.kg) — Government judicial decisions are public information under Kyrgyz law.
