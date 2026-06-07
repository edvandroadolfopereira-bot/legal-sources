# LU/Competition — Luxembourg Competition Authority

Decisions and opinions from the **Autorité de la concurrence** (formerly Conseil de la concurrence) of the Grand Duchy of Luxembourg.

## Data Source

- **Primary**: [data.public.lu](https://data.public.lu/en/organizations/conseil-de-la-concurrence/) — Open data portal datasets for 2012–2018 decisions and opinions
- **Supplementary**: PDF documents hosted at `concurrence.public.lu/dam-assets/` for additional years (2019+, pre-2012)

## Coverage

- ~80–100 competition decisions and opinions (2012–2024)
- Categories: cartels (ententes), abuse of dominant position, mergers, interim measures, fines, commitments, opinions (avis)
- Language: French (some documents in German)
- Full text extracted from PDF documents

## Strategy

1. Query data.public.lu API for all datasets published by the Conseil de la concurrence
2. Download PDF resources from each decision dataset
3. Check supplementary dam-assets URLs for decisions not on the open data portal
4. Extract text from PDFs using pdfplumber

## License

[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) — Public domain. Government decisions published on Luxembourg's open data portal.
