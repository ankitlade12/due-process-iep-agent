# Due Process — an IEP enforcement agent

> **From one-time IEP review to continuous, evidence-backed delivery review.**
>
> The incumbents prepare you for the IEP meeting. This one holds the school accountable *after* it.

Millions of US students receive services under IDEA through an Individualized
Education Program (IEP). When delivery records are fragmented, families and
advocates must reconstruct what was promised, what happened, and which questions
to raise—often under filing deadlines.

**Due Process** is a grounded compliance agent that tracks whether a school
actually delivers what the IEP describes, documents potential gaps, estimates a
starting point for discussion, and drafts a review packet—**with factual claims
tied to source records, authorities selected from a controlled corpus, and a human
approving every external action.**

Built for the Qwen Cloud hackathon, **Track 4 (Autopilot Agent)**: an end-to-end
workflow with a human checkpoint at every critical decision.

## What makes it novel — and who it helps

It's open-source infrastructure for the people who already help families for free,
not another paid consumer app. Four ideas, layered:

1. **Continuous evidence, not just meeting prep.** Existing products also help
   families track delivery and draft communications. Due Process differentiates
   itself with an open, deterministic ledger, source-level provenance, explicit
   review thresholds, and reproducible evaluation.
2. **Privacy-gated pattern review.** With authorization across a caseload, it can
   aggregate de-identified shortfalls using a k-anonymity threshold and draft a
   request for broader investigation. It does not determine liability or guarantee
   district-wide relief. (`python -m due_process.examples.systemic_demo`)
3. **A force-multiplier for the under-resourced.** Federally-funded Parent
   Training & Information centers, legal clinics, and pro-bono advocates handle
   substantial caseloads. This is an open, multi-case workflow they can inspect
   and adapt.
4. **Built for access.** "Receipts, not lawsuits" — it starts as a friendly
   record you keep, escalation optional. And it speaks the parent's language: the
   plain-language summary translates via Qwen, because the enforcement system
   silently assumes an English-fluent, sophisticated parent and most families
   aren't.

## The core design principle: deterministic core, bounded LLM

The thing that makes this credible (and not "trust the LLM") is a hard boundary:

| **Deterministic code** (unit-tested, auditable) | **Qwen LLM** (bounded, fills fixed scaffolds) |
|---|---|
| Minutes arithmetic: required vs delivered vs excused | Classify a free-text missed reason as excused / unexcused |
| Configurable review threshold (not a legal bright line) | Extract service commitments from messy IEP text |
| Statute-of-limitations math | Summarize the pattern in plain language |
| Prior Written Notice 7-element checklist | Draft the letter narrative into a fixed legal template |

**No LLM ever does the math or the law lookup.** Every flagged violation is grounded
to three things a parent can click and verify: the IEP provision, the service-log
entries that show the shortfall, and a controlled IDEA/state authority corpus.
The publication gate rejects citations that do not resolve to that corpus and
shortfalls that lack source IDs. This reduces unsupported output; it does not
guarantee the corpus is complete or that an authority controls a particular case.

## The agent workflow (Track 4)

```
ingest IEP text + raw service logs
  → extract service commitments        [checkpoint: human confirms parsed values]
  → classify missed-session reasons    [checkpoint: human resolves ambiguous]
  → run the deterministic analysis     (auditable math — no checkpoint needed)
  → draft the right instrument         (service-log request / state complaint)
  → approve before sending             [checkpoint: human approval]
  → send (timestamped audit entry)
```

The agent never classifies an ambiguous reason on its own and never sends an
unapproved instrument. Every step is recorded in an audit trail.

## Reproducible evaluation

The repository ships a labeled evaluation and prominently reports false-positive
rate. The stable, network-free comparison is:

| metric | **grounded** | offline heuristic baseline |
|---|---|---|
| precision | 1.00 | 0.78 |
| recall | 1.00 | 1.00 |
| false-positive rate | **0.00** | 0.50 |
| citation accuracy | **1.00** | 0.00 |
| compensatory-minutes MAE | **0.0** | n/a |

Reproduce it with `python -m due_process.evaluation.run_eval --offline`. The
explicit `--online` mode compares against live raw Qwen, but those results can vary
by model version and are not the repository benchmark.

**Honest caveat:** most labels are synthetic and constructed to the system's own
materiality rule, so the headline is the *contrast* with the baseline (lower FPR,
no unverifiable citations), not proof the threshold is legally perfect. A few
cases now carry **independent, documented labels** — e.g. *Van Duyn*, where a
court held a 50% tutoring shortfall material — which the system also gets right.
Full validation still needs a corpus of advocate-labeled de-identified IEPs (on
the roadmap).

## Quick start

```bash
uv venv
uv pip install -e ".[dev,llm,ingest,demo]"

# 1) Deterministic core — reproduce the spec's worked example (108 vs 72 sessions):
python -m due_process.examples.worked_example

# 2) Full Track 4 workflow — extract → classify → analyze → draft → approve → send:
python -m due_process.examples.agent_demo

# 3) Systemic evidence — a district of families → one de-identified district complaint:
python -m due_process.examples.systemic_demo

# 4) Scanned-IEP vision — Qwen reads a (synthetic) IEP image, then it's parsed:
python -m due_process.examples.vision_demo

# 5) Stable evaluation — grounded system vs offline heuristic baseline:
python -m due_process.evaluation.run_eval --offline

# 6) Live advocate case desk: Qwen/rules prepare inputs, a human edits and
# confirms them, deterministic analysis runs, then an approved packet can be
# stored through Function Compute with a verifiable OSS receipt.
streamlit run src/due_process/examples/case_desk.py

# Test suite (all offline):
uv run --extra dev pytest
```

Or use the installed CLI on real files:

```bash
due-process analyze --logs service_log.csv --service speech --freq 3 \
    --duration 30 --periods 36 --state NY --draft --packet complaint_packet.txt
due-process pwn --file prior_written_notice.txt        # check the 7 elements
due-process vision --image scanned_iep.png --redacted-or-synthetic
```

## Demo and submission docs

- [`docs/architecture.md`](docs/architecture.md) - Qwen Cloud, deterministic core,
  grounding, human approval, and Alibaba Function Compute deployment view.
- [`docs/TWO_PERSON_DEMO_SCRIPT.md`](docs/TWO_PERSON_DEMO_SCRIPT.md) - 2:10-2:30
  recording script for two presenters.
- [`docs/SUBMISSION.md`](docs/SUBMISSION.md) - Devpost-facing project description
  and longer 3-minute script.
- [`docs/PRODUCT_STRATEGY.md`](docs/PRODUCT_STRATEGY.md) - the sharper evidence
  flight-recorder wedge, judge story, defensibility, and 30-day roadmap.

Everything above runs **with no API key**, using transparent rule-based / template
fallbacks. To use Qwen for messy real-world inputs, add a key:

```bash
cp .env.example .env          # then paste your Qwen Cloud key into DASHSCOPE_API_KEY
```

## Qwen Cloud integration

The LLM layer targets Qwen Cloud's OpenAI-compatible endpoint
(`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`). Model roles:

- **`qwen3.7-max`** — orchestration, reasoning, and the letter narrative
- **`qwen3.7-plus`** — default workhorse for extraction/classification
- **`qwen3.7-plus`** — multimodal scanned-IEP reading; the Function Compute demo
  also uses it as the low-latency deployed workhorse

The code is provider-pluggable: every Qwen-backed task has a deterministic
fallback, so the system degrades gracefully to offline rules and upgrades to Qwen
the moment `DASHSCOPE_API_KEY` is present.

Verify the live integration (exercises extraction, classification, and narrative
against the real endpoint):

```bash
python -m due_process.examples.qwen_smoketest
```

### Proof of deployment (Alibaba Cloud)

The project calls the **Qwen Cloud (Alibaba Cloud)** API. The base URL is in
[`src/due_process/llm/client.py`](src/due_process/llm/client.py) —
`https://dashscope-intl.aliyuncs.com/compatible-mode/v1` — and is used by every
LLM call, by the live check `python -m due_process.examples.qwen_smoketest`, and
by the Function Compute handler in [`deploy/`](deploy/) (`handler.py` + `s.yaml`),
which reports whether Model Studio completed each task or a safe local fallback
was used. Token Plan users override the base URL via `DUE_PROCESS_LLM_BASE_URL`
(see `.env.example`).

## Package layout

```
due_process/
  models.py          data model (commitments, logs, ledger, violations, ...)
  corpus.py          legal grounding corpus (IDEA CFR / U.S.C. / case law)
  ledger.py          deterministic promised-vs-delivered minutes math
  materiality.py     material-failure rule + violation detection + comp estimate
  deadlines.py       filing-deadline clock: 1-yr state complaint + 2-yr due process
  pwn.py             Prior Written Notice 7-element checklist (34 CFR 300.503(b))
  grounding.py       evidence-by-ID; rejects ungrounded claims
  analysis.py        the deterministic pipeline the agent calls per commitment
  agent.py           Track 4 orchestrator with human-in-the-loop checkpoints
  privacy.py         direct-identifier redaction before text cloud calls
  ingest.py          real-document ingestion (CSV/PDF logs, Qwen-vision IEP)
  store.py           SQLite case store + the deadline guard (alerts/agenda)
  filing.py          per-state filing guidance + filable evidence packet
  systemic.py        de-identified, k-anonymous cross-family aggregation
  scenarios.py       synthetic scenarios with ground-truth labels
  llm/               bounded LLM layer (client + classification/extraction/narrative)
  instruments/       fixed cited templates + the human approval gate
  evaluation/        labeled dataset + metrics + grounded-vs-baseline runner
  examples/          runnable demos
```

## Built for real records, not just clean demos

The features that move it from "correct engine on synthetic data" to "a parent or
advocate can run it on a real child's actual records":

- **Privacy-minimizing text path** (`privacy.py`) — known direct identifiers are
  redacted before text reaches a cloud model. Automated redaction is not a FERPA
  compliance guarantee: users must upload only synthetic or already-de-identified
  records to the public demo. Cloud vision requires an explicit redaction/synthetic
  attestation because output-only redaction cannot protect the input image.
- **Ingests what people actually have** (`ingest.py`) — service logs from CSV/TSV
  (with fuzzy header mapping and status inference), text from PDFs, and **scanned
  IEPs read by Qwen's vision model**.
- **A year-round tool with a deadline guard** (`store.py` + `deadlines.py`) — a
  SQLite case store that remembers across the year and surfaces an *agenda*: what's
  material, what's owed, and which deadline is approaching. It tracks the two
  *different* clocks correctly — a **1-year** window for a state complaint (34
  C.F.R. 300.153(c)) vs. **2 years** for due process (20 U.S.C. 1415) — a trap
  that otherwise makes parents miss the real, shorter deadline.
- **Make-up reconciliation** (`ledger.py`) — when the school makes up a missed
  session, that shortfall is marked cured and drops out of what's owed.
- **Human-review packet** (`filing.py`) — per-state filing guidance plus an exported
  **evidence packet**: the complaint, a numbered exhibit index (the IEP line + the
  exact log entries), and the cited authorities, ready to send.

## Not legal advice

This is information and drafting support, not legal advice. A human approves every
action. Legal specifics are the federal floor and must be localized and verified
against your state's special-education regulations before reliance.

The early discovery brief is retained as an explicitly archived artifact; current
product claims and behavior are documented here and in `docs/`.
