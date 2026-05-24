# CV/TribunalSupremo — Cabo Verde Supreme Court Decisions

Fetches court decisions (acórdãos) from the Supremo Tribunal de Justiça de Cabo Verde.

## Coverage

- **Civil section** (~47 decisions) — direct PDF links from section page
- **Administrative/Fiscal section** (~27 decisions) — direct PDF links from section page
- **Criminal section** (~104 decisions) — via WordPress Download Manager on main acordaos page
- **Total**: ~178 decisions (2019–2024)

## Data Access

The STJ website uses WordPress with the Download Manager plugin. Two access methods:

1. **Section pages** (`/1a-sec-civel/`, `/3a-sec-adm-fisc-ad/`) — expose direct `wp-content/uploads/*.pdf` links
2. **Main acordaos page** (`/index.php/acordaos/`) — WPDM download pages that require resolving `data-downloadurl` attributes to get the PDF URL with `?wpdmdl=ID&refresh=TOKEN`

## License

[Public Domain](https://www.stj.cv/) — Official judicial decisions of the Republic of Cabo Verde. Court decisions are public records under Cabo Verdean law.
