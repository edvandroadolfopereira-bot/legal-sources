# SD/TaxAuthority — Sudan Taxation Chamber

Full text of Sudan's tax legislation and the Taxation Chamber's official tax
guidance, from the Chamber's portal at [tax.gov.sd](https://tax.gov.sd).

## Data

Two complementary, open, no-auth sources:

1. **Legislation** — the consolidated English tax Acts published as PDFs on the
   [tax-laws page](https://tax.gov.sd/en/tax-laws/): the Income Tax Act 1986,
   the Stamp Duty Act 1986 and the Capital Gains Tax Act 1986. Downloaded and
   extracted to full text (`_type: legislation`).
2. **Doctrine** — the Chamber's official tax-guidance pages, served through the
   WordPress REST API (`wp-json/wp/v2/pages`). These reproduce the operative
   rules for each tax (procedures, levy, scope, exemptions, appeals, sanctions)
   plus business-profits tax and double-taxation agreements, in English and
   Arabic (`_type: doctrine`).

The site also hosts scanned (image-only) and broken-font Arabic PDFs that yield
no usable text; these are filtered out by a Latin/Arabic readability check, so
every emitted record contains genuine full text.

## Usage

```bash
python bootstrap.py test               # connectivity check
python bootstrap.py bootstrap --sample # save sample records
python bootstrap.py bootstrap          # full pull
python bootstrap.py update             # incremental (WP modified_after)
```

## Record schema

`_id`, `_source` (`SD/TaxAuthority`), `_type` (`legislation` | `doctrine`),
`_fetched_at`, `title`, `text` (full body), `date`, `url`, `category`.

## License

[Open Government Data](https://tax.gov.sd/) — Sudanese government tax
legislation and official guidance, published by the Taxation Chamber for public
use. Sudanese legislation (statutes, regulations) is government work in the
public domain; the Chamber's guidance pages are official public information. No
attribution requirement or commercial-use restriction is stated. Commercial use
permitted.
