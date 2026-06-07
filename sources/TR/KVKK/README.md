# TR/KVKK — Turkey Personal Data Protection Authority

The **Kişisel Verileri Koruma Kurumu** (KVKK) is Turkey's data protection authority,
established under Law No. 6698 on the Protection of Personal Data (2016).

## Data Coverage

This source fetches three categories of published decisions:

1. **Kurul Karar Özetleri** (Decision Summaries) — ~256 individual enforcement decisions
   covering data breaches, unlawful processing, and administrative fines
2. **İlke Kararları** (Principle Decisions) — ~18 policy/principle decisions
3. **Kurul Kararları** (Board Decisions) — ~20 formal regulatory decisions

## Access Method

HTML scraping of kvkk.gov.tr content pages. No API available.

- List pages use pagination: `?page=N`
- Individual decisions at: `https://www.kvkk.gov.tr/Icerik/{ID}/{slug}`

## License

[Turkish Law No. 5846, Art. 31](https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5846.pdf) —
Official texts of laws, regulations, and decisions of state authorities are not subject
to copyright protection under Turkish intellectual property law.
