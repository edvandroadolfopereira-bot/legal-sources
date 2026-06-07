# MK/AEC-Decisions — North Macedonia Agency for Electronic Communications

The **Agency for Electronic Communications** (Агенција за електронски комуникации,
"АЕК"; English: AEK/AEC) is North Macedonia's independent telecom and
electronic-communications regulator, established under the Law on Electronic
Communications. It publishes its regulatory output on [aek.mk](https://aek.mk/):
decisions and resolutions (одлуки/решенија), rulebooks and regulations
(правилници), sector legislation, and plans. Most items are official reprints
from the Official Gazette (Службен весник).

## What this source collects

- **Decisions & resolutions** (`odluki-i-reshenija`) — regulatory decisions.
- **Legislation** (`legislativa`) — the Law on Electronic Communications and the
  agency's rulebooks/regulations (правилници).
- **Competition legislation** (`konkurencija-legislativa`).
- **Plans** (`planovi`) — numbering plans, spectrum plans, etc.

Each document's **full text** is extracted from the linked PDF (most are
born-digital gazette reprints). Image-only scans are dropped by a Cyrillic /
long-token quality filter. Content is in Macedonian. `_type` is `doctrine`.

## How it works

The site runs WordPress with the REST API enabled. Posts are listed per
category via `/wp-json/wp/v2/posts?categories=ID`, returning structured JSON
(title, date, body). The PDF link is parsed from each post body, downloaded,
and text-extracted with `pdfplumber`.

## Usage

```bash
python bootstrap.py test-api            # count posts per category
python bootstrap.py bootstrap --sample  # 15 sample records
python bootstrap.py bootstrap           # full pull
```

## License

[Public Domain (Government of North Macedonia)](https://aek.mk/) — official
regulatory acts, decisions and Official Gazette reprints published by the state
telecom regulator (AEK) for public access. Commercial use permitted.
