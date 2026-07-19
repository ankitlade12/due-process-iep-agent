# Security and privacy

## Credential incident

If a key appears in chat, a screenshot, commit, terminal recording, or build log,
treat it as compromised. Revoke it in the provider console, create a new key,
remove the exposed copy, and review provider audit/billing logs. Merely editing
`.env` does not revoke a credential.

Never commit `.env`. Use `.env.example` for variable names only.

## Data policy

The public demo accepts only synthetic or already-de-identified records. Direct-
identifier redaction is defense in depth, not a FERPA guarantee. Do not upload a
real image unless it was redacted before upload and you are authorized to process
it. Define retention, deletion, access logging, encryption, and incident-response
policies before any real deployment.

## Application boundary

The public Streamlit workspace accepts synthetic or already-de-identified inputs
and does not email, file, or upload its generated packet. Downloaded artifacts
remain under the reviewer's control. Add authentication, retention controls,
monitoring, rate limiting, and a secret manager before any private deployment.

## Reporting

Do not open a public issue containing sensitive records or credentials. Contact
the repository owner privately with a minimal reproduction and no student data.
