# PK/PakistanLaws-HuggingFace — Pakistan Laws Dataset (federal legislation)

Full text of **967 federal laws and acts of Pakistan**, sourced from the
Ministry of Law and Justice website ([pakistancode.gov.pk](https://pakistancode.gov.pk/))
and redistributed as a single JSON file on HuggingFace:
[`AyeshaJadoon/Pakistan_Laws_Dataset`](https://huggingface.co/datasets/AyeshaJadoon/Pakistan_Laws_Dataset).

Each dataset record is `{file_name, text}` where `text` is the full body of a
statute (originally a PDF, converted to text). This source is a usable mirror
of `PK/PakistanCode`, which is blocked because pakistancode.gov.pk is
unreliable from datacenter IPs.

## Data access

- Download `pdf_data.json` (~47 MB) directly via the HuggingFace
  `resolve/main/` URL — no auth required.
- The auto-converted parquet split is empty, so the datasets-server **rows
  API does not work**; the raw file download is the only path.
- Titles and enactment years are derived from the document text because the
  PDF file names are opaque hashes (e.g. `administrator<hash>.pdf`). The
  canonical original document is at `pakistancode.gov.pk/pdffiles/{file_name}`.

## Normalized record

| field | description |
|-------|-------------|
| `_id` | `PK-LAW-{file_stem}` |
| `_type` | `legislation` |
| `title` | statute title derived from the text (e.g. *THE ISLAMABAD HIGH COURT ACT, 2010*) |
| `text` | full statute text (whitespace-cleaned) |
| `date` / `year` | enactment year (e.g. `2010`), or null when not detectable |
| `url` | canonical origin PDF on pakistancode.gov.pk |
| `file_name` | original dataset file name |

## Usage

```bash
python bootstrap.py test               # connectivity check
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap          # full pull (967 records)
```

## License

[ODC-BY 1.0](https://opendatacommons.org/licenses/by/1-0/) — attribution required, commercial use permitted.

The dataset is published under ODC-BY 1.0 on HuggingFace. The underlying
documents are Government of Pakistan federal legislation published by the
Ministry of Law and Justice (pakistancode.gov.pk), which are public legal
texts.
