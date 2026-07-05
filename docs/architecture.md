# Architecture

**Due Process** is a Track 4 Autopilot Agent for IEP service-delivery
enforcement. The core design choice is a hard boundary between:

- **Qwen Cloud**, which handles messy language tasks.
- **Deterministic Python**, which handles math, materiality, deadlines,
  grounding, and approval state.
- **A human approval gate**, which blocks every outbound action.

## Demo System

```mermaid
flowchart TD
    USER["Parent / advocate / judge"] --> DESK["Streamlit case desk"]
    DESK --> RUN["Run live Qwen review"]
    DESK --> PREVIEW["Fast local preview"]

    RUN --> QWEN["Qwen Cloud Model Studio"]
    PREVIEW --> RULES["Local rule-based fallback"]

    QWEN --> EXTRACT["Extract IEP commitments"]
    QWEN --> CLASSIFY["Classify missed-session reasons"]
    QWEN --> NARRATIVE["Draft narrative language"]

    RULES --> EXTRACT
    RULES --> CLASSIFY

    EXTRACT --> LEDGER["Deterministic ledger"]
    CLASSIFY --> LEDGER
    LEDGER --> MATERIALITY["Materiality and comp estimate"]
    MATERIALITY --> GROUNDING["Evidence and legal grounding"]
    GROUNDING --> DRAFT["Draft complaint / remedy"]
    NARRATIVE --> DRAFT
    DRAFT --> APPROVAL["Human approval checklist"]
    APPROVAL --> HOLD["Draft held; no send in demo"]

    LEDGER --> SYSTEMIC["District-wide k-anonymous pattern"]
    SYSTEMIC --> SYS_DRAFT["Systemic complaint draft"]
```

The demo UI is not a static mock. It calls the same backend modules used by the
CLI and tests: extraction, classification, ledger, materiality, grounding,
instrument drafting, systemic aggregation, and approval policy.

## Agent Boundary

| Layer | Responsibility | Why it matters |
|---|---|---|
| Qwen Cloud | IEP commitment extraction, missed-reason classification, narrative language | Handles ambiguous real-world records without giving it legal authority |
| Deterministic core | Required vs delivered minutes, materiality threshold, deadline math, compensatory estimate | Keeps the auditable decisions reproducible and testable |
| Grounding layer | Links every claim to IEP text, log rows, and legal references | Prevents unsupported allegations and hallucinated citations |
| Human approval | Confirm parsed values, resolve ambiguous reasons, approve drafts | Keeps the agent from taking legal or outbound action alone |

The LLM never computes the ledger, decides materiality, selects a legal deadline,
or invents citations. Ambiguous classifications become checkpoints.

## Backend Flow

```mermaid
flowchart LR
    IEP["IEP text / scanned IEP"] --> REDACT["FERPA redaction"]
    LOGS["Service logs"] --> INGEST["Log ingestion"]
    REDACT --> QEX["Qwen or rules: commitment extraction"]
    INGEST --> QCL["Qwen or rules: reason classification"]
    QEX --> ANALYSIS["Analysis pipeline"]
    QCL --> ANALYSIS
    ANALYSIS --> LED["Ledger"]
    LED --> MAT["Materiality"]
    MAT --> DEADLINE["Deadline clock"]
    MAT --> COMP["Compensatory estimate"]
    DEADLINE --> CLAIMS["Grounded claims"]
    COMP --> CLAIMS
    CLAIMS --> INSTRUMENT["Fixed cited instrument template"]
    INSTRUMENT --> GATE["Approval gate"]
    GATE --> AUDIT["Audit trail"]
```

## Alibaba Cloud Deployment View

```mermaid
flowchart LR
    CLIENT["Demo / API caller"] --> FC["Alibaba Cloud Function Compute"]
    FC --> MODEL["Qwen Cloud Model Studio<br/>OpenAI-compatible API"]
    FC --> CORE["Deterministic Python package"]
    CORE --> CORPUS["Legal corpus and evidence IDs"]
    CORE --> RESPONSE["JSON: ledger, claims, drafts, audit"]
```

The deployed proof path lives in `deploy/`. `handler.py` invokes the package and
uses the Qwen Cloud base URL from `due_process.llm.client`. The response reports
`"llm": "qwen-online"` when Model Studio was called successfully.

## Safety and Privacy

- FERPA-sensitive fields are redacted before cloud model calls.
- Draft instruments are held for human review.
- The demo does not send anything externally.
- Systemic aggregation uses k-anonymity before producing district-level findings.
- The local preview path exists for rehearsal and offline tests, but the primary
  demo path is the live Qwen Cloud review.

## Verification Surface

- `uv run pytest` covers the deterministic core and the case desk payload.
- `python -m due_process.examples.qwen_smoketest` verifies live Qwen extraction,
  classification, and narrative calls.
- `streamlit run src/due_process/examples/case_desk.py` runs the judge-facing
  demo workspace.
- `deploy/handler.py` is the Alibaba Function Compute entrypoint for deployment
  proof.
