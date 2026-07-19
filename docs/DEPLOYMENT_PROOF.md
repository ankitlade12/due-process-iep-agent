# Alibaba Cloud deployment proof

Verified on July 19, 2026 against the deployed Function Compute resource. This
record contains no credential values or student data.

## Resource

- Service: Alibaba Cloud Function Compute 3.0
- Function: `due-process-agent`
- Region: `ap-southeast-1`
- Runtime: Python 3.10
- Memory: 1024 MB
- Trigger: anonymous HTTP (`GET`, `POST`) for the synthetic proof route
- Public endpoint: `https://due-pross-agent-bjhlmitbbr.ap-southeast-1.fcapp.run`

Custom case requests remain disabled unless an application Bearer token is
configured. The public proof route uses only the repository's synthetic worked
example.

## Verified invocation

Command:

```bash
cd deploy
s invoke -e '{}'
```

Function Compute request ID:
`1-6a5d1012-01e62d-9bce6918f94c`

Observed result:

```json
{
  "ok": true,
  "qwen": {
    "configured": true,
    "successful_calls": 4,
    "failed_calls": 0,
    "extraction_methods": ["qwen"],
    "classification_methods": ["qwen"],
    "fallbacks": []
  },
  "models": {
    "orchestrator": "qwen3.7-plus",
    "workhorse": "qwen3.7-plus"
  },
  "analyses": [{
    "required_minutes": 3240,
    "delivered_minutes": 2160,
    "unexcused_shortfall_minutes": 720,
    "review_signal": true
  }],
  "needs_human": true
}
```

Function logs recorded four successful HTTP 200 responses from the Qwen Cloud
Model Studio compatible endpoint. The generated instrument remained in `draft`
state with the final approval checkpoint unresolved, demonstrating that successful
model execution does not bypass the human-action boundary.

## Required visual evidence

This reproducible record supplements but does not replace the Devpost screenshot.
The submission must also include an Alibaba Cloud Workbench or Function Compute
console screenshot showing this deployed resource, with all credential values
hidden.
