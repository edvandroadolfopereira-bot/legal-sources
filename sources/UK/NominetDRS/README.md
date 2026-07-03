# UK/NominetDRS — Nominet Dispute Resolution Service (DRS) Decisions

Decisions of **Nominet's Dispute Resolution Service (DRS)**, the administrative
procedure that resolves disputes over `.uk` domain-name registrations. Nominet
is the official registry for `.uk` domains. When a complainant alleges that a
domain is an *abusive registration* of a name or mark in which they have rights,
an Independent Expert issues a decision — either a short **Summary Decision** or
a fully reasoned **Full Decision** — ordering a transfer, cancellation, or no
action.

This is a sizeable, openly-published body of `.uk` domain-name case law (the
DRS has run since 2001, with several hundred decisions per year).

## Data access

- **Search tool:** <https://secure.nominet.org.uk/drs/search-disputes.html>
- A session cookie is established with a `GET`, then a `POST`
  (`action.showAllDecisions`) lists all decisions, most recent first, 10 per page.
- Pagination uses `?action.browseBasicSearchResults=y&page=N`.
- Each result row carries a `decisionDocumentId`; a `POST`
  (`action.viewDecisionDocument`) returns the decision **PDF**.
- Full text is extracted from the PDF via the shared `pdf_extract` backend.

No authentication, login, or paywall — all decisions are public.

## Record schema

| Field | Description |
|-------|-------------|
| `_id` / `case_number` | DRS case number, e.g. `D00029141` |
| `title` | Synthesised (case number, domain, parties) |
| `text` | Full text extracted from the decision PDF |
| `date` | Decision date (ISO 8601) |
| `domain_name` | Disputed `.uk` domain |
| `complainant`, `respondent` | Parties |
| `decision_type` | `Summary Decision` or `Full Decision` |
| `outcome` | `Transfer`, `No Action`, etc. |

## Usage

```bash
python bootstrap.py test               # connectivity + one-decision check
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap          # full corpus
```

## License

> ⚠️ **Commercial use restricted.** Decisions are publicly accessible without
> login, but Nominet reserves IP rights and permits only personal/internal
> reference. Commercial reuse requires a licence from Nominet.

[© Nominet UK — Terms of Use](https://nominet.uk/terms-of-use/) — all rights
reserved; attribution to Nominet expected. Flagged commercial-restricted.
