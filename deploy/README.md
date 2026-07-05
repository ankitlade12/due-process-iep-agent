# Deployment — Alibaba Cloud Function Compute

This directory is the hackathon's **Proof of Alibaba Cloud Deployment**: a code
file that demonstrates Alibaba Cloud API usage. The deployed function runs the
Due Process enforcement agent, which on every request calls **Qwen Cloud Model
Studio** — the Alibaba Cloud OpenAI-compatible endpoint
(`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) — for the bounded LLM
steps (extraction, classification, narrative), while the deterministic core does
all the math and the law.

## What Devpost requires (two parts)

1. **A code file that uses the Qwen Cloud base URL** — ✅ satisfied. The base URL
   `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` is in
   `../src/due_process/llm/client.py` and is what `handler.py` here calls on
   every request. (Token Plan: override with
   `https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`.)
2. **A screenshot of running resources in the Alibaba Cloud Workbench** — you
   provide this after `s deploy`: screenshot the **Function Compute** console
   showing the `due-process-agent` function (and/or an invocation log), or the
   Qwen Cloud usage/logs page showing the API calls. Attach it to the Devpost
   submission.

## Files

| File | Role |
|---|---|
| [`handler.py`](handler.py) | Function Compute entrypoint; runs the agent and returns JSON |
| [`s.yaml`](s.yaml) | Serverless Devs (v3) config for Function Compute 3.0 |
| [`build.sh`](build.sh) | Bundles `due_process` + the Qwen SDK + the handler into `./dist` |
| `requirements.txt` | Runtime dependency (`openai`, used as the Qwen client) |

## Deploy

```bash
# 0) Prereqs: Node, and the Serverless Devs CLI
npm install -g @serverless-devs/s

# 1) Authenticate to Alibaba Cloud (AccessKey ID/Secret), alias "default"
s config add

# 2) Your Qwen Cloud key (the function reads it as an env var)
export DASHSCOPE_API_KEY=sk-...

# 3) Bundle and deploy
cd deploy
./build.sh
s deploy

# 4) Invoke — no payload runs the worked example; or pass your own:
s invoke
s invoke -e '{"iep_text":"Speech-Language Therapy: 3 x 30 minutes per week, individual.","instructional_periods":36,"window_start":"2025-09-02","window_end":"2026-05-09","logs":[{"date":"2025-09-04","status":"missed","minutes_delivered":0,"missed_reason_text":"Provider absent, no substitute"}]}'
```

The HTTP trigger also exposes a URL (printed by `s deploy`) you can `curl` for the
demo video.

## What the response shows

```json
{
  "llm": "qwen-online",
  "models": {"orchestrator": "qwen3.7-plus", "workhorse": "qwen3.7-plus"},
  "analyses": [{"material_failure": true, "unexcused_shortfall_minutes": 720,
                "compensatory_minutes": 720, "deadline": "2028-05-09"}],
  "instruments": [{"type": "state_complaint", "status": "draft", "...": "..."}],
  "audit": ["[extract] ...", "[analyze] ...", "[draft] ..."]
}
```

`"llm": "qwen-online"` confirms the deployed function called Qwen Cloud Model
Studio. Instruments come back as **drafts** — sending stays a human decision.

## Local check (no cloud account needed)

You can run the exact handler logic locally before deploying:

```bash
python deploy/handler.py        # runs handler(None, None) and prints the JSON
```
