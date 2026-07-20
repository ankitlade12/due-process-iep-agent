# Alibaba Cloud deployment proof

Verified on July 19, 2026 CDT against the deployed Function Compute resource.
This record contains no credential values or student data.

## Resource

- Service: Alibaba Cloud Function Compute 3.0
- Function: `due-process-agent`
- Region: `ap-southeast-1` (Singapore)
- Runtime: Python 3.10
- Memory: 1024 MB
- Trigger: Function-authenticated HTTP (`GET`, `POST`)
- Public-system hostname:
  `due-pross-agent-bjhlmitbbr.ap-southeast-1.fcapp.run`
- Source definition: [`../deploy/s.yaml`](../deploy/s.yaml)
- Entrypoint and security boundary:
  [`../deploy/handler.py`](../deploy/handler.py)

The endpoint accepts only a health operation and the packaged synthetic proof.
It rejects custom student records, storage, email, and filing actions. Function
Compute authentication prevents it from acting as an anonymous Qwen proxy.

## Verified Qwen-backed invocation

Signed command:

```bash
cd deploy
s invoke -e '{"action":"synthetic-proof"}'
```

Function Compute request ID:
`1-6a5d94b4-0141de-002822eb23ce`

Observed sanitized result:

```json
{
  "ok": true,
  "platform": "Alibaba Cloud Function Compute",
  "region": "ap-southeast-1",
  "action": "synthetic-proof",
  "qwen": {
    "successful_calls": 4,
    "failed_calls": 0,
    "extraction_methods": ["qwen"],
    "classification_methods": ["qwen"]
  },
  "deterministic_result": {
    "required_minutes": 3240,
    "delivered_minutes": 2160,
    "unexcused_shortfall_minutes": 720,
    "review_signal": true
  },
  "human_control": {
    "needs_human": true,
    "draft_statuses": ["draft"],
    "approve_instrument_resolved": false
  }
}
```

Function logs recorded four successful HTTP 200 responses from the Qwen Cloud
Model Studio compatible endpoint. The invocation took 113.4 seconds. Qwen
performed bounded extraction, reason classification, and drafting; deterministic
code computed the ledger; the final instrument remained a draft with human
approval unresolved.

## Devpost visual evidence

The Devpost submission also requires a screenshot from Alibaba Cloud. Capture
the Function Compute console showing the function name, region, Python runtime,
authenticated HTTP trigger, and a successful invocation. Hide all environment
variable values, AccessKeys, and tokens before uploading the screenshot.
