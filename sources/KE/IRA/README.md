# KE/IRA — Kenya Insurance Regulatory Authority

Kenya's Insurance Regulatory Authority (IRA) regulates the insurance industry
under the Insurance Act (Cap 487). This source fetches regulatory circulars,
guidelines, and legal notices via the IRA's custom AJAX API.

## Data types

- **doctrine**: Circulars, guidelines, legal notices, and regulatory documents

## Strategy

Custom AJAX API at `assets/includes/ajapp.php`:
- POST with base64-encoded JSON parameters for each section
- 8 sections: circulars (insurers, agents, brokers, service providers,
  reinsurers, intermediaries), guidelines, and legal notices
- ~121 resources total, PDFs downloaded via `lib.html?f={slug}`
- Text extracted from PDFs using pdfplumber
- Scanned-image PDFs (no extractable text) are skipped

## License

[Public Government Documents (Kenya)](https://www.ira.go.ke/) — official
regulatory publications. Attribution required.
