# NA/BON-Regulations — Bank of Namibia

The **Bank of Namibia** (BoN, [bon.com.na](https://www.bon.com.na/)) is Namibia's
central bank and banking-sector regulator. It publishes its legal framework —
determinations, regulations, circulars, guidelines, directives and other bylaws —
issued under the Banking Institutions Act, the Bank of Namibia Act, the Payment
System Management Act, the Financial Intelligence Act and related statutes. Each
document is an official Government Gazette notice.

## What this source collects

Regulatory instruments from across the `/Regulations/` tree (and the Banking
Supervision legal-framework pages):

- **Determinations** — prudential rules under the Banking Institutions Act.
- **Regulations** — gazette regulations on banking/payment matters.
- **Circulars, Guidelines, Directives, Other Bylaws** — supervisory instruments.

Each document's **full text** is extracted from its Government Gazette PDF.
`_type` is `doctrine`. Content is in English.

## How it works

The site runs a Kentico CMS. The scraper does a bounded breadth-first crawl of
the `/Regulations/` tree, collecting document links. Each document is served via
the Kentico attachment handler at `/getattachment/{guid}/.aspx`; the PDF is
downloaded and text-extracted with `pdfplumber`. Image-only scans are dropped by
a Latin-text quality filter. A crawl discovers ~150 documents.

## Usage

```bash
python bootstrap.py test-api            # crawl + count document links
python bootstrap.py bootstrap --sample  # 15 sample records
python bootstrap.py bootstrap           # full pull
```

## License

[Public Domain (Government of Namibia)](https://www.bon.com.na/) — official
Government Gazette notices and regulatory acts published by the Bank of Namibia
for public access. Commercial use permitted.
