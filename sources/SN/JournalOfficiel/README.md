# Senegal Official Gazette (Journal Officiel)

**Source:** [https://primature.sn/publications/lois-et-reglements](https://primature.sn/publications/lois-et-reglements)
**Country:** SN
**Data types:** legislation
**Status:** Complete

## Description

Official legislation from Senegal: codes, laws, decrees, and administrative orders
published by the Primature (formerly Secrétariat Général du Gouvernement).

The original source at jo.gouv.sn is unreachable; primature.sn hosts the same content.

Sections scraped:
- **Codes** (~18 items): Consolidated law codes (Penal, Electoral, Mining, etc.)
- **Lois et Décrets** (~40 items): Individual laws and presidential decrees

## Strategy

HTML scraping of the Drupal 9-based primature.sn website:
1. Paginate listing pages for codes and lois-et-décrets sections
2. Fetch each document page
3. Extract full text from `div.field--name-body`

## License

[Public Domain (Government Works)](https://primature.sn/) — Official Senegalese government publications are public domain.
