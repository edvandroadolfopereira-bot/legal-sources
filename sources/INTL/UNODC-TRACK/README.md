# INTL/UNODC-TRACK — UNODC TRACK Anti-Corruption Legal Library

Fetches anti-corruption legislation submitted by 180+ UNCAC States parties to
the UNODC TRACK (Tools and Resources for Anti-Corruption Knowledge) Legal
Library. Records are article-level provisions of national laws mapped to
specific UNCAC chapters and articles.

- Front-end: https://track.unodc.org/track/en/legal-library/index.html
- Search API: `https://www.unodc.org/cld/en/trackview/data.json?lng=en&criteria={...}`
- Detail API: `https://www.unodc.org/cld/trackview/x2j.jspx?uri=<uri>`

The search API returns ~80,500 article entries (light metadata). The detail
endpoint returns a JSON document whose `originalText.html` field contains the
full body of each article, which this scraper extracts and strips.

## Run

```bash
python bootstrap.py test                   # connectivity probe
python bootstrap.py bootstrap --sample     # ~15 sample records
python bootstrap.py bootstrap              # full bootstrap (~80K records)
```

## License

[United Nations / UNODC Terms of Use](https://www.unodc.org/unodc/en/terms-of-use.html) — UN materials are generally free to reuse with attribution. TRACK aggregates national legislation submitted by States parties under the UNCAC Implementation Review Mechanism.
