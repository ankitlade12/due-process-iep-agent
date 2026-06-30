# Architecture

**Due Process** — an IEP enforcement agent (Qwen Cloud hackathon, Track 4:
Autopilot Agent).

## The one idea

A hard boundary between a **deterministic core** that does all the math and the
law lookup, and a **bounded Qwen LLM** that only handles messy language and fills
fixed scaffolds. A human approves every outbound action. Every claim is grounded
to a verifiable source, so a hallucinated citation is impossible by construction.

## System flow

```mermaid
flowchart TD
    IEP["IEP PDF / text"]
    LOGS["Service logs (school or parent)"]

    subgraph QWEN["Bounded LLM — Qwen Cloud (OpenAI-compatible)"]
      EX["extract commitments<br/>(qwen3.6-flash)"]
      CL["classify reasons<br/>excused / unexcused / ambiguous"]
      NA["narrative<br/>(qwen3.7-max)"]
    end

    subgraph DET["Deterministic core — NO LLM (unit-tested)"]
      LED["ledger<br/>required vs delivered minutes"]
      MAT["materiality rule<br/>(Van Duyn standard)"]
      DL["statute-of-limitations clock"]
      COMP["compensatory estimate<br/>(Reid — equitable)"]
    end

    subgraph GR["Grounding"]
      COR["legal corpus<br/>IDEA CFR / U.S.C. / case law"]
      EV["evidence by ID<br/>rejects ungrounded claims"]
    end

    subgraph OUT["Instruments + human-in-the-loop"]
      DR["fixed cited templates<br/>service-log request · state complaint · PWN"]
      AP["human approval gate<br/>DRAFT → APPROVED → SENT"]
    end

    IEP --> EX --> C1{"checkpoint:<br/>confirm parsed values"} --> LED
    LOGS --> CL --> C2{"checkpoint:<br/>resolve ambiguous"} --> LED
    LED --> MAT
    MAT --> COMP
    MAT --> DL
    MAT --> EV
    COR --> EV
    EV --> DR
    COMP --> DR
    DL --> DR
    NA --> DR
    DR --> AP --> SEND["send + timestamped audit entry"]
```

## The deterministic / LLM split

| Deterministic code (auditable) | Qwen LLM (bounded) |
|---|---|
| Minutes arithmetic, the ledger | Classify a free-text missed reason |
| Materiality threshold | Extract commitments from a messy IEP |
| Statute-of-limitations math | Plain-language summary |
| PWN 7-element checklist | Letter narrative into a fixed template |

The LLM never decides materiality, never computes minutes, and never authors the
legal scaffolding or the citations. Ambiguous classifications are flagged for a
human, never auto-resolved.

## Deployment view (Qwen Cloud + Alibaba Cloud)

```mermaid
flowchart LR
    U["Parent / advocate"] --> API["API Gateway"]
    API --> FC["Function Compute<br/>ingest · ledger · draft"]
    FC --> MS["Qwen Cloud Model Studio<br/>qwen3.7-max / 3.6-flash / 3.7-plus"]
    FC --> OSS["OSS<br/>IEPs, logs, drafts (encrypted)"]
    FC --> RDS["ApsaraDB RDS PostgreSQL<br/>ledger · violations · deadline clock"]
    FC --> REDIS["ApsaraDB Redis<br/>prompt cache"]
```

The deterministic core and the bounded LLM layer are deployment-agnostic Python
today; the proof-of-deployment wraps the agent in a Function Compute handler that
invokes Qwen Cloud Model Studio (the Alibaba Cloud API the hackathon requires).

## Privacy (FERPA)

IEPs and service logs are student education records (FERPA, 20 U.S.C. 1232g; 34
C.F.R. Part 99). PII is redacted before any cloud model call, or the open-weight
Qwen model runs in a private VPC so identifiable records never leave the parent's
control. Encrypted at rest and in transit; no training on uploads.
