# JM/FSC-Guidelines — Financial Services Commission (Jamaica)

Guidelines, bulletins, and notices from the Financial Services Commission of
Jamaica (FSC), the regulator of the securities, insurance, and private-pension
industries.

## Coverage

- **Guidelines** (~96) — prudential & capital standards, market conduct,
  collective investment schemes, issuer disclosure, fitness & propriety,
  cyber-risk management, actuarial valuation, stress testing
- **Bulletins** (~93) — supervisory advisories and industry notices
- **Notices** (~19) — public/regulatory notices

Documents are PDFs hosted under `/wp-content/uploads/`. Posts are enumerated via
the WordPress REST API (`/wp-json/wp/v2/posts`), and each post's linked PDF is
downloaded and text-extracted with pdfminer. When a PDF has no text layer
(e.g. scanned supplementary tables), the post's inline HTML content is used as a
fallback; records with no usable text are skipped. English language.

## Access

Open, no authentication. WordPress REST API + public PDF downloads.

## License

[Open Government Data](https://www.fscjamaica.org/) — official regulator guidance
documents published for public access on the FSC Jamaica government-agency
website. No explicit license deed; treated as open government data (commercial
use permitted).
