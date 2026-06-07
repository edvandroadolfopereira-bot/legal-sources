# RW/CMA-Regulations — Rwanda Capital Market Authority

Capital-markets legal framework published by the **Capital Market Authority
(CMA) of Rwanda** at [cma.rw](https://www.cma.rw/). Complements the existing
`RW/Amategeko` (general legislation) and `RW/BNR` (central bank / banking)
sources with Rwanda's securities and capital-markets regulation.

## What this covers

The CMA's **Regulatory Framework** section publishes ~30 instruments across:

- **Laws** — Law establishing the CMA, Law regulating capital markets business,
  Law governing Collective Investment Schemes, Law governing trusts, Law on the
  Central Securities Depository, Law regulating Virtual Asset Business.
- **Regulations** — Capital Market Corporate Governance Code, CSD operations,
  licensing of CSD operators, Real Estate Investment Trusts, leveraged FX
  trading, AML administrative sanctions, fees, financial reporting, credit
  rating agencies.
- **Guidelines** — GSS+ bond issuance, Fintech Regulatory Sandbox, prevention of
  ML/FT in capital markets, commercial paper issuance, SME disclosure.
- **Orders** — ministerial orders (inspections/investigations, CMA operations).
- **Directives** — CMA directives and East African Community (EAC) directives.

Instruments are published trilingually (Kinyarwanda / English / French) in
Official Gazette of Rwanda format.

## How it works

The site runs **TYPO3**. Each category page (`/regulatory-framework/{category}`)
lists instruments as `docs-item` cards carrying a title, a date, and a direct
PDF download under `/fileadmin/user_upload/`. The scraper:

1. Fetches each category page and parses the cards (title, date, PDF URL).
2. Deduplicates by PDF URL (an instrument may sit in two categories).
3. Downloads each PDF and extracts full text with `pdfplumber`.

All PDFs are born-digital with clean text layers; ~30 instruments yield full
text (median ~102K characters per document).

## Run

```bash
python bootstrap.py test                 # connectivity check
python bootstrap.py bootstrap --sample   # write sample records
python bootstrap.py bootstrap            # full pull
```

## License

[Public Domain — Government of Rwanda](https://www.cma.rw/) — these are official
legal instruments of a Rwandan statutory regulator, published in the Official
Gazette of Rwanda. Commercial use permitted; no attribution required.
