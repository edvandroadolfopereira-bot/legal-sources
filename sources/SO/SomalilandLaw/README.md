# SO/SomalilandLaw

Somaliland Law — comprehensive collection of Somaliland legislation from
somalilandlaw.com, maintained by the International Journal of Somaliland Law.

600+ PDFs covering constitution, penal code, civil code, election laws,
judiciary laws, military codes, and official gazettes. Documents in English,
Somali, Italian (historical codes), and Arabic.

**Method:** Crawl topic pages → discover PDF links → download + text extraction via pdfplumber.

**Note:** Site only supports HTTP (no HTTPS). Some historical PDFs are scanned
images without OCR and will yield no text.

## Usage

```bash
python bootstrap.py test                  # Test connectivity
python bootstrap.py bootstrap --sample    # Fetch 15 key English law PDFs
python bootstrap.py bootstrap --full      # Full bootstrap (all 600+ PDFs)
```

## License

[Open Academic Access](http://www.somalilandlaw.com/) — Official government legislation hosted by academic journal. Attribution recommended.
