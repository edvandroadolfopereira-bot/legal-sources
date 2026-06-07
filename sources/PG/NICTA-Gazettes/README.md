# PG/NICTA-Gazettes — Papua New Guinea National ICT Authority

Telecom/ICT legislation and regulatory instruments published by the **National
Information and Communications Technology Authority (NICTA)** of Papua New Guinea
at [nicta.gov.pg](https://www.nicta.gov.pg/).

## What this covers

NICTA is PNG's telecom/ICT regulator. Its "Regulatory" and "Legislative" sections
publish the country's ICT legal framework as PDF instruments. This source captures
the full text of the extractable instruments, including:

- **National Information and Communication Technology Act 2009** (primary statute, ~225 pp.)
- **Cybercrime Policy 2014**
- **NICTA (Operator Licensing) Regulation 2010**, **NICTA (Radio Spectrum) Regulation 2010**
- **SIM Card Registration Regulation 2016**
- **Telecommunications Quality of Service (QoS) Rule 2022**, **ICT Equipment Type Approval Rule 2022**
- **Reference Interconnection Offer Rule 2012**
- **Standard and Special Conditions of Individual Licences Rule 2025**
- **National Numbering Plan 2016**
- **Consumer Complaints Management System Guideline 2025**

## How it works

The site runs WordPress. Legal instruments live in the `legislative` / `regulatory`
category tree and are exposed through the **WordPress REST API**
(`/wp-json/wp/v2/posts`). Each post embeds its instrument as a PDF (an Adobe
PDF-embed block carrying a `data-media-url`, or a direct `.pdf` link). The scraper:

1. Queries the WP REST API for posts in the legal-instrument categories.
2. Extracts the embedded PDF URL from each post.
3. Downloads the PDF and extracts full text with `pdfplumber`.
4. Skips older **scanned, image-only PDFs** that have no text layer
   (the two National Gazette notices, the two Wholesale Service Declarations,
   and the scanned Cybercrime Code Act 2016 scan — ~5 documents).

~11 instruments yield clean full text.

## Run

```bash
python bootstrap.py test                 # connectivity check
python bootstrap.py bootstrap --sample   # write sample records
python bootstrap.py bootstrap            # full pull
```

## License

[Public Domain — Government of Papua New Guinea](https://www.nicta.gov.pg/) —
NICTA is a PNG statutory body; the legislation, regulations, rules, and
guidelines it publishes are official government legal instruments in the public
domain. Commercial use permitted; no attribution required.
