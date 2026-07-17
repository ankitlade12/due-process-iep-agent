# Security and privacy

## Credential incident

If a key appears in chat, a screenshot, commit, terminal recording, or build log,
treat it as compromised. Revoke it in the provider console, create a new key,
remove the exposed copy, and review provider audit/billing logs. Merely editing
`.env` does not revoke a credential.

Never commit `.env`. Use `.env.example` for variable names only. Use a separate,
least-privilege OSS identity in production; do not reuse a broad deployment key.

## Data policy

The public demo accepts only synthetic or already-de-identified records. Direct-
identifier redaction is defense in depth, not a FERPA guarantee. Do not upload a
real image unless it was redacted before upload and you are authorized to process
it. Define retention, deletion, access logging, encryption, and incident-response
policies before any real deployment.

## API boundary

The unauthenticated Function Compute route runs a synthetic example only. Custom
records require a Bearer token configured through `DUE_PROCESS_API_TOKEN`. OSS
storage additionally requires an explicit approval flag. Put the API behind HTTPS,
rate limiting, monitoring, and a secret manager/API gateway for production.

## Reporting

Do not open a public issue containing sensitive records or credentials. Contact
the repository owner privately with a minimal reproduction and no student data.
