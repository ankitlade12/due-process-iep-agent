# Deployment — Alibaba Cloud Function Compute

This directory contains the deployable Track 4 backend. It runs bounded Qwen
language tasks, deterministic analysis, draft generation, and an optional
human-approved Alibaba OSS artifact action.

## Security contract

- An unauthenticated empty request runs the synthetic worked example only.
- Any payload containing a custom IEP or logs requires
  `Authorization: Bearer $DUE_PROCESS_API_TOKEN`.
- OSS storage happens only on an authenticated custom case with
  `"approval":{"store_evidence_packet":true}`.
- Use synthetic or already-de-identified demo data. Automated redaction is not a
  FERPA compliance guarantee.
- Use a separate least-privilege OSS identity. Never reuse a broad deployment key.

## Files

| File | Role |
|---|---|
| `handler.py` | validates/authenticates requests and runs the agent |
| `s.yaml` | Function Compute 3.0 definition |
| `build.sh` | builds Linux CPython 3.10 deployment wheels |
| `requirements.txt` | Qwen-compatible client; OSS signing uses the stdlib |

## Configure and deploy

Rotate any previously exposed key before these steps.

```bash
npm install -g @serverless-devs/s
s config add

export DASHSCOPE_API_KEY="ROTATED_VALUE"

cd deploy
./build.sh
s deploy
s invoke
```

OSS is optional. To enable approval-gated storage later, configure
`DUE_PROCESS_OSS_BUCKET`, `DUE_PROCESS_OSS_ENDPOINT`,
`DUE_PROCESS_OSS_ACCESS_KEY_ID`, and `DUE_PROCESS_OSS_ACCESS_KEY_SECRET` on the
deployed function using a least-privilege identity.

The initial synthetic proof route does not need an application token. To enable
custom de-identified case requests, generate a long random value and configure it
as `DUE_PROCESS_API_TOKEN` on the deployed function; callers must send the same
value as a Bearer token.

The empty invocation returns a synthetic draft plus actual-call provenance. It
does not infer “Qwen online” merely because a key exists.

Set the deployed trigger URL on the Streamlit host (not inside Function Compute):

```bash
export DUE_PROCESS_FUNCTION_URL="https://your-function-trigger-url"
```

## Public Streamlit frontend on Render

The repository root includes `render.yaml` for the public presentation layer.
Create a Render Blueprint from the repository, provide the three secret values
when prompted, and keep Function Compute as the required Alibaba Cloud backend:

- `DASHSCOPE_API_KEY` — a rotated Qwen Cloud key;
- `DUE_PROCESS_FUNCTION_URL` — the deployed Function Compute HTTP trigger; and
- `DUE_PROCESS_API_TOKEN` — the same application token configured on Function
  Compute when authenticated custom requests or optional storage are enabled.

The Blueprint uses Render's free plan to avoid an automatic charge. Free services
can cold-start after being idle; upgrade manually only if the account owner chooses
to accept the cost. Do not upload `.env` or paste cloud AccessKeys into Render.

## Authenticated synthetic/de-identified custom request

```bash
curl -X POST "$FUNCTION_URL" \
  -H "Authorization: Bearer $DUE_PROCESS_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @deploy/sample-request.json
```

Add `"approval":{"store_evidence_packet":true}` to the local sample copy to
exercise OSS. A successful response includes:

```json
{
  "ok": true,
  "qwen": {
    "successful_calls": 2,
    "failed_calls": 0,
    "extraction_methods": ["qwen"]
  },
  "analyses": [{"review_signal": true}],
  "artifact_receipt": {
    "provider": "alibaba-oss",
    "uri": "oss://private-bucket/evidence-packets/...",
    "sha256": "..."
  }
}
```

The exact call count may vary. For submission proof, capture Alibaba Workbench
showing the deployed Function Compute resource and a safe synthetic invocation;
ensure the screenshot contains no secret or student data.

The case desk uses a narrower action after the human reviews the packet. It sends
the exact approved packet with `"action":"store_evidence_packet"`; Function
Compute verifies the Bearer token and approval flag, stores the bytes in OSS, and
returns a matching SHA-256 receipt.

Use `sample-store-request.json` for a synthetic command-line proof:

```bash
curl -X POST "$FUNCTION_URL" \
  -H "Authorization: Bearer $DUE_PROCESS_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @deploy/sample-store-request.json
```

## Local boundary check

Disable the local key explicitly so `.env` cannot trigger a network call:

```bash
DASHSCOPE_API_KEY= python deploy/handler.py
pytest tests/test_deploy_handler.py
```
