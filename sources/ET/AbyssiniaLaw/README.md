# ET/AbyssiniaLaw — Abyssinia Law Ethiopian Legal Information Portal

Ethiopian legal documents from [abyssinialaw.com](https://www.abyssinialaw.com/),
including Federal Supreme Court cassation decision volumes, federal and regional
constitutions, and recent proclamations.

## Data Coverage

- **Cassation Decisions**: ~28 volumes of Federal Supreme Court cassation decisions (Amharic)
- **Constitutions**: Federal constitution + 10+ regional state constitutions (Amharic & English)
- **Latest Laws**: Recent proclamations and codes (Amharic & English)
- **Format**: PDF download with text extraction

## Usage

```bash
python bootstrap.py test               # Test connectivity
python bootstrap.py bootstrap --sample # Fetch 15 sample records
python bootstrap.py bootstrap          # Fetch all documents
python bootstrap.py bootstrap --full   # Fetch all and push to Neon
```

## License

[Abyssinia Law Terms of Use](https://www.abyssinialaw.com/about-us) — independent legal portal maintained by Liku Worku Law Office. Ethiopian government legal documents (laws, constitutions, court decisions) are public domain under Ethiopian law.
