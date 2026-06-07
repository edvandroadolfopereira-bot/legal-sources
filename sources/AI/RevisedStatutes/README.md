# AI/RevisedStatutes — Revised Statutes and Regulations of Anguilla

Official legislation portal maintained by the Regional Law Revision Centre for the Government of Anguilla.

- **URL**: https://laws.gov.ai
- **Coverage**: 2022 Revised Edition (~629 acts and regulations with PDFs)
- **Data type**: legislation
- **Format**: PDF (text extracted via pdfplumber)

## Strategy

The site is a Laravel/Livewire app. The initial HTML embeds Livewire snapshot JSON containing structured row data (chapter number, title, PDF path). Pagination is handled via URL parameter `&page=N`. PDFs are served from `/storage/{path}`.

## License

> ⚠️ **Commercial use restricted.** See terms below.

[Government of Anguilla — All rights reserved](https://laws.gov.ai/?selected_page=disclaimer) — unofficial online edition; official copies available from the Attorney General's Chambers.
