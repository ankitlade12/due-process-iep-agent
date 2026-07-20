# Alibaba Cloud Function Compute backend

This directory is the deployment proof required by the Qwen Cloud hackathon. It
deploys a Python 3.10 backend to Alibaba Cloud Function Compute in Singapore and
invokes Qwen Cloud Model Studio for a packaged synthetic workflow.

## Safety boundary

- `health` reports deployment metadata without calling Qwen.
- `synthetic-proof` runs only the repository's synthetic worked example.
- Custom IEP text, student logs, storage, email, and filing are rejected.
- The HTTP trigger uses Function Compute authentication; it is not an anonymous
  Qwen proxy and cannot be used by public callers to spend model quota.
- Drafts remain unapproved and every consequential calculation is deterministic.
- No credential values belong in this repository or in screenshots.

## Deploy

```bash
npm install -g @serverless-devs/s
s config add
cd deploy
./build.sh
s deploy
```

The deployment reads `DASHSCOPE_API_KEY` from the deployer's environment and
stores it as a Function Compute environment variable. Never place its value in
`s.yaml`.

## Verify

Health check without a model call:

```bash
s invoke -e '{"action":"health"}'
```

Qwen-backed synthetic proof:

```bash
s invoke -e @sample-proof-request.json
```

The proof response reports Function Compute metadata, per-call Qwen provenance,
deterministic ledger totals, and the unresolved human-approval state. Capture the
Function Compute console and successful synthetic invocation for Devpost with all
environment-variable values hidden.
