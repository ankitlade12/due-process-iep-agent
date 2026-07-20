# Architecture

Due Process has one strict boundary: Qwen interprets bounded language inputs;
deterministic code owns consequential calculations, publication checks, and
workflow state. A human confirms interpretations before they affect the ledger.

[![Due Process runtime architecture](architecture.png)](architecture.pdf)

```mermaid
flowchart LR
    U["Parent / advocate"] --> UI["Streamlit case desk on Render"]
    UI --> R["Direct-identifier redaction"]
    R --> Q["Qwen Cloud: extract / classify / draft"]
    R --> F["Transparent local fallback"]
    Q --> P["Actual-call provenance + fallback reasons"]
    Q --> C1["Human confirms commitment"]
    F --> C1
    C1 --> C2["Human resolves ambiguous reasons"]
    C2 --> D["Deterministic ledger / review policy / deadlines"]
    D --> G["Evidence-ID and corpus publication gate"]
    G --> H["Human reviews draft"]
    H --> DL["Reviewer-controlled packet download"]
```

## Alibaba Cloud deployment boundary

The public Streamlit workspace runs on Render. The hackathon deployment backend
runs the same packaged synthetic workflow on Alibaba Cloud Function Compute:

```mermaid
flowchart LR
    I["Signed Serverless Devs invocation"] --> FC["Function Compute 3.0"]
    FC --> Q["Qwen Cloud Model Studio"]
    Q --> P["Per-call provenance"]
    FC --> D["Deterministic ledger"]
    D --> H["Draft remains pending human review"]
```

The Function Compute trigger requires platform authentication. It accepts only
health and packaged synthetic-proof operations; custom records, storage, email,
and filing actions are rejected. This keeps the required Alibaba backend
demonstrable without creating a public Qwen proxy or a second student-data path.

## Responsibility map

| Layer | Owns | Cannot claim |
|---|---|---|
| Qwen Cloud | service extraction, narrative-reason classification, bounded prose | legal conclusion, ledger math, or successful use when it fell back |
| Deterministic core | minutes, windows, review threshold, deadline indicators | that a configurable threshold is the law |
| Grounding gate | source IDs and controlled corpus resolution | that the corpus is complete or an authority controls a case |
| Human gate | confirms interpretation and reviews the draft | automated legal representation or external action |
| Product surface | redacted intake, audit trail, evidence display, packet download | permission to send, file, or upload the packet |
| Function Compute proof backend | authenticated synthetic Qwen workflow and deployment evidence | custom student records or outbound actions |

## Runtime sequence

```mermaid
sequenceDiagram
    participant U as Reviewer
    participant S as Streamlit workspace
    participant Q as Qwen Cloud
    participant D as Deterministic core

    U->>S: synthetic or de-identified IEP text + logs
    S->>Q: redacted bounded language task
    Q-->>S: structured output + provenance
    S-->>U: editable commitment and ambiguity review
    U->>S: confirm source interpretation
    S->>D: confirmed commitment + classified records
    D-->>S: ledger, screening signal, deadlines, grounded claims
    S-->>U: evidence packet + draft for review/download
```

## Privacy model

- The public UI permits only synthetic or already-de-identified inputs.
- Known direct identifiers are removed before text-model calls, but automated
  redaction is not a FERPA compliance certification.
- Images are riskier because the cloud receives pixels before returning text;
  vision refuses an image without a redacted/synthetic attestation.
- Cross-case pattern analysis requires authority for each case, pseudonyms, and a
  k-anonymity reporting threshold.
- The public workspace does not email, file, or upload generated packets.

## Verification

- `uv run --extra dev pytest` — offline unit and boundary tests.
- `python -m due_process.evaluation.run_eval --offline` — synthetic policy
  regression; implementation consistency, not real-world accuracy.
- `python -m due_process.evaluation.run_eval --online` — exploratory live-Qwen
  contrast; variable and not a benchmark.
- `streamlit run src/due_process/examples/case_desk.py` — product workflow.
