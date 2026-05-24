# IQ/KRG-Legislation — Kurdistan Region Parliament Legislation

Official legislation database of the Kurdistan Region Parliament (Iraq).
Contains 400+ laws and 150+ legal orders enacted from 1992 to 2022 in
Unicode Kurdish (Sorani dialect).

- **Source:** https://legislation.krd/
- **Parliament site:** https://www.parliament.krd/
- **Language:** Kurdish (Sorani), some Arabic
- **Coverage:** 1992–2022
- **Data type:** Legislation (laws and legal orders)
- **Sub-jurisdiction:** IQ-AR (Kurdistan Region / Erbil)

## Strategy

1. Crawl year-based listing pages (`/years/?year=YYYY`) for laws (1992-2022)
2. Crawl paginated order listings (`/orders-law?pageNumber=N`)
3. For each entry, fetch the detail page (`/law-detail/?id=NNNN`)
4. Extract full text from the HTML body of the detail page

## License

[Open government data](https://legislation.krd/) — official parliamentary publication, freely accessible.
