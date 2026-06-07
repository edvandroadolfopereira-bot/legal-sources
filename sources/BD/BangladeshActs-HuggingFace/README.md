# BD/BangladeshActs-HuggingFace

Bangladesh Legal Acts Dataset from HuggingFace (sakhadib/Bangladesh-Legal-Acts-Dataset).

## Overview

- **Records:** 1,484 legal acts (1799–2025)
- **Content:** Full text with structured sections, footnotes, government context
- **Languages:** English, Bengali, mixed
- **Original source:** bdlaws.minlaw.gov.bd (Ministry of Law, Justice and Parliamentary Affairs)
- **Format:** Single consolidated JSON file (~62 MB)

## Data Fields

| Field | Description |
|-------|-------------|
| act_title | Official title of the act |
| act_no | Act number (Roman numerals) |
| act_year | Year of enactment |
| sections | Array of {section_title, section_content} |
| footnotes | Array of {footnote_text} |
| government_context | Historical government info at time of enactment |
| legal_system_context | Legal framework context |
| is_repealed | Whether the act has been repealed |
| token_count | Token count for the full text |

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — Attribution required. Dataset by [sakhadib](https://huggingface.co/sakhadib) on HuggingFace.
