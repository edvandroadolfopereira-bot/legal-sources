# Kyrgyzstan State Agency for Communications — Decisions (KG/GKTS-Telecom)

**Source:** [https://nas.gov.kg/](https://nas.gov.kg/)
**Country:** KG
**Data types:** doctrine
**Status:** Complete

## Overview

Normative acts and regulatory decisions of the Kyrgyz telecommunications
regulator. The body has been renamed several times — historically the State
Agency for Communications (GKTS), then the National Communications Agency
(NAS), and currently the **Service for Regulation and Supervision in the
Communications Sector under the Ministry of Digital Development** (СРНОС/SRNOS).
Its public site remains `nas.gov.kg`.

Content covered:

- Licensing rules and license-control regulations (положения, инструкции)
- Certification rules
- Radio-frequency spectrum rules
- Numbering-resource regulations and allocation orders (приказы)
- Methodological recommendations and reporting/inspection forms

## How it works

1. The scraper crawls the regulator's topic pages under `/dp/` and collects
   linked PDF documents.
2. Each PDF is downloaded and its full text extracted with `pdfplumber`.
3. A quality filter keeps born-digital documents with clean Cyrillic text and
   drops heavily-scanned PDFs whose OCR text is garbled.

The site serves an **expired TLS certificate**, so the scraper disables HTTPS
verification (`verify=False`). Content is in Russian.

## Usage

```bash
python bootstrap.py test-api            # count PDF links per section
python bootstrap.py bootstrap --sample  # sample records for validation
python bootstrap.py bootstrap           # full pull
```

## License

Public Domain (Government of the Kyrgyz Republic) — official regulatory acts
and decisions published by the state communications regulator for public
access. No license deed URL is published; commercial use is permitted.
