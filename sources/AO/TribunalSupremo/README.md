# AO/TribunalSupremo — Angola Supreme Court

Court decisions (acórdãos) from Angola's Tribunal Supremo.

## Data Source

- **URL**: https://tribunalsupremo.ao
- **API**: WordPress REST API (`/wp-json/wp/v2/posts`)
- **Format**: PDF attachments with extractable text
- **Language**: Portuguese
- **Coverage**: ~490 decisions across 5 chambers

## Chambers

| Category ID | Chamber | Count |
|-------------|---------|-------|
| 163 | Câmara Criminal | ~303 |
| 209 | Câmara do Cível, Administrativo, Fiscal e Aduaneiro | ~163 |
| 165 | Câmara do Trabalho | ~21 |
| 166 | Câmara Familiar | ~1 |
| 162 | Plenário | ~2 |

## Usage

```bash
python bootstrap.py bootstrap --sample   # Fetch 15 sample records
python bootstrap.py bootstrap            # Fetch all decisions
python bootstrap.py test                 # Test connectivity
```

## License

Public domain — official court decisions under Angolan law.
