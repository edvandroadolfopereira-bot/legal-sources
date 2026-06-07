# NA/CRAN-Decisions — Communications Regulatory Authority of Namibia

The **Communications Regulatory Authority of Namibia** (CRAN,
[cran.na](https://www.cran.na/)) is Namibia's independent regulator for
telecommunications, broadcasting, postal services and radio spectrum,
established under the Communications Act (No. 8 of 2009). CRAN files its
regulatory output — regulations, determinations, decisions, withdrawals and
notices — in the Government Gazette and collects every such issue on its
**Government Gazettes** page.

## What this source collects

CRAN's gazetted regulatory instruments (~295 gazette issues), plus the named
final-regulation pages. Each document's **full text** is extracted from its
Government Gazette PDF. A descriptive title is built from the gazette CONTENTS
(the CRAN notice headings), e.g. *"GG 8841: CRAN — Amendment of Regulations
prescribing the provision of Universal Service…"*. `_type` is `doctrine`.
Content is in English.

## How it works

CRAN runs WordPress (the REST API is disabled). The `/government-gazettes/`
page lists gazette PDFs under `/wp-content/uploads/`; each is downloaded and
text-extracted with `pdfplumber`. Image-only scans are dropped by a Latin-text
quality filter.

## Usage

```bash
python bootstrap.py test-api            # list + count gazette PDFs
python bootstrap.py bootstrap --sample  # 15 sample records
python bootstrap.py bootstrap           # full pull
```

## License

[Public Domain (Government of Namibia)](https://www.cran.na/) — official
Government Gazette notices and regulatory acts published by CRAN for public
access. Commercial use permitted.
