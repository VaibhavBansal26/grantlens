# Privacy and data handling

This describes what GrantLens does today, including its gaps. It is a technical description, not legal
advice or a privacy policy; if real users' data is involved, have the institution's privacy office review it.

## What is stored, per account

| Data | Where | Notes |
|---|---|---|
| Email address | `user_account` | Lower-cased. Used to sign in and for alert and reset emails. |
| Password | `user_account.password_hash` | Salted hash (werkzeug scrypt). The password itself is never stored or logged. |
| Saved searches | `saved_search` | The search text and filters you chose to save, and whether email alerts are on. |
| Watchlist | `watched_opportunity` | Which grants you watch. |
| Uploaded documents | `document`, `doc_chunk` | **Extracted text only**, split into passages with embeddings. The PDF file itself is not kept. |
| Literature reviews | `review` | The generated review (themes, annotations, paper list). |
| Alert settings and history | `saved_search.alerts`, `user_account.reminders`, `deadline_reminder` | So alerts are not repeated. |
| AI usage counter | `llm_usage` | Requests per day, to enforce the daily limit. No content. |

Shared grant and award data (Grants.gov, NIH RePORTER, NSF) is public and is not tied to any user.

## What is not stored

- The text of ordinary searches (`/search`, `/match`, `/literature/search`). They are processed and discarded.
- Request logs record method, path, status, duration, request id and the numeric user id. They do **not**
  record query strings, request bodies, IP addresses, passwords or tokens.
- Session cookie: one cookie (`HttpOnly`, `SameSite=Lax`, `Secure` in production). No analytics, no trackers, no third-party scripts.

## Who else receives data

| Recipient | What is sent | When |
|---|---|---|
| **OpenAI** | Document passages and your question (document Q&A); the grant text and what you wrote about yourself or your ORCID papers (fit check); paper titles and abstracts (review builder); short topic strings (search-query writing) | Only when you use those AI features, and only if the operator has set `OPENAI_API_KEY`. Retention is governed by the operator's OpenAI account settings and OpenAI's terms: check them before uploading anything confidential. |
| **OpenAlex** | Search text and ORCID iDs | Paper search, "find grants for my work" with an ORCID, fit check, review builder. |
| **Sentry** (optional) | Error reports: stack trace, route and status. Query strings, bodies, cookies, headers, IP addresses and user details are removed before sending. | Only if the operator sets `SENTRY_DSN` and installs the `observability` extra. Off by default. |
| **Email provider (SMTP)** | Your address and the alert or reset message | Only when alerts or password resets are used. |

**Do not upload unpublished or confidential documents unless you are comfortable with them being sent to
OpenAI.** The Documents page says documents are read by an AI service; keep that wording.

## Your controls

- **Delete my account** (Account page, or `DELETE /auth/account` with your password) permanently removes
  the account and every row listed above. Shared grant data is untouched.
- **Delete a document or a review** individually at any time.
- **Stop emails:** every alert email has a one-click unsubscribe link, and the toggles can be turned off on the
  Saved searches and Watchlist pages.
- A password reset signs out every device.

## Retention

- **Uploaded documents expire automatically** after `RETENTION_DOCUMENT_DAYS` (default 90; 0 turns it off), when
  `flask retention` runs (schedule it daily). Each document in the app shows its deletion date. AI usage counters
  are deleted after 30 days and sent-reminder markers after 180.
- Saved searches, the watchlist and reviews are things you curate on purpose, so they stay until you delete them.
- Alert and reminder emails go only to addresses confirmed through the link we email at sign-up.
- **Backups** (`scripts/backup.sh`) contain whatever existed when they were taken. A deleted account
  disappears from backups only as old backups are rotated out (14 by default). Keep that in mind when answering deletion requests.

## Security measures in place

HTTPS is expected in front of the web port (terminate TLS at a reverse proxy or load balancer).
Passwords hashed; login, registration, password-reset and AI endpoints rate-limited (per address and, for
login and reset, per account); sessions invalidated on password reset; reset links expire after one hour and
work once; production refuses to start with a weak `SECRET_KEY`; the API is not exposed directly (only the
web app's `/api` proxy is) and CORS is closed by default; responses carry `nosniff`, `no-referrer` and
`no-store`; uploaded text and model output are shown as plain text, and emails escape user-controlled text;
the model is told document text is untrusted, and every quote it returns is checked against the source.
Dependencies were audited (`pip-audit`, `npm audit`) with no known vulnerabilities at the time of writing.

## Known gaps

- **No email verification:** anyone can register an address they do not own (they cannot read mail sent to it).
- **Registration reveals whether an email is already registered** (HTTP 409). Login and password-reset do not.
- **PDF parsing runs inside the API process.** Size and page limits apply, but a hostile PDF is parsed with
  the same privileges as the API. Isolating it in a separate, sandboxed worker would be safer.
- **No audit log** of sign-ins or deletions, and no admin tooling for data requests.
- **Operator access:** anyone with database access can read saved searches and document text. Restrict it.
