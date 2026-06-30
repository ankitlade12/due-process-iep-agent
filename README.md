# Due Process — an IEP enforcement agent

> **From IEP review, which is crowded, to IEP enforcement, which is open.**
>
> The incumbents prepare you for the IEP meeting. This one holds the school accountable *after* it.

Over 8 million K–12 students in the US have a legal right under IDEA to specific
special-education services written into an Individualized Education Program (IEP).
The IEP is a legally binding contract — and schools routinely under-deliver. The
enforcement burden falls entirely on the parent, and private advocates run
$150–$250/hr, so most families go without.

**Due Process** is a grounded compliance agent that tracks whether a school
actually delivers what the IEP promised, proves the gap when it does not, computes
what the child is owed, and drafts the remedy — **with every claim cited to a real
legal source and a human approving every outbound action.**

Built for the Qwen Cloud hackathon, **Track 4 (Autopilot Agent)**: an end-to-end
workflow with a human checkpoint at every critical decision.

## The core design principle: deterministic core, bounded LLM

The thing that makes this credible (and not "trust the LLM") is a hard boundary:

| **Deterministic code** (unit-tested, auditable) | **Qwen LLM** (bounded, fills fixed scaffolds) |
|---|---|
| Minutes arithmetic: required vs delivered vs excused | Classify a free-text missed reason as excused / unexcused |
| Materiality threshold (the *material failure* standard) | Extract service commitments from a messy IEP |
| Statute-of-limitations math | Summarize the pattern in plain language |
| Prior Written Notice 7-element checklist | Draft the letter narrative into a fixed legal template |

**No LLM ever does the math or the law lookup.** Every flagged violation is grounded
to three things a parent can click and verify: the IEP provision, the service-log
entries that show the shortfall, and the governing IDEA/state regulation. A
hallucinated citation is impossible by construction — every cite is validated
against the corpus, and every shortfall must point at the log entries the
deterministic ledger counted.

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

## Published evaluation (the credibility story)

Every incumbent's accuracy claim is unfalsifiable marketing. This one ships a
labeled eval and reports the numbers — including the one that matters most, the
false-positive rate (telling a parent they have a case when they do not). Against
an ungrounded baseline with no ledger and no corpus:

| metric | **grounded** | baseline |
|---|---|---|
| precision | 1.00 | 0.75 |
| recall | 1.00 | 1.00 |
| false-positive rate | **0.00** | 0.50 |
| citation accuracy | **1.00** | 0.00 |
| compensatory-minutes MAE | **0.0** | n/a |

(Offline figures use a transparent heuristic baseline; with a Qwen key the
baseline is raw Qwen prompted to find violations and cite the law from memory.)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,llm]"

# 1) Deterministic core — reproduce the spec's worked example (108 vs 72 sessions):
python -m due_process.examples.worked_example

# 2) Full Track 4 workflow — extract → classify → analyze → draft → approve → send:
python -m due_process.examples.agent_demo

# 3) The evaluation — grounded system vs an ungrounded baseline:
python -m due_process.evaluation.run_eval

# Test suite (84 tests, all offline):
pytest
```

Everything above runs **with no API key**, using transparent rule-based / template
fallbacks. To use Qwen for messy real-world inputs, add a key:

```bash
cp .env.example .env          # then paste your Qwen Cloud key into DASHSCOPE_API_KEY
```

## Qwen Cloud integration

The LLM layer targets Qwen Cloud's OpenAI-compatible endpoint
(`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`). Model roles:

- **`qwen3.7-max`** — orchestration, reasoning, and the letter narrative
- **`qwen3.6-flash`** — the cheap workhorse for high-volume extraction/classification
- **`qwen3.7-plus`** — multimodal, for scanned IEP PDFs and photographed logs

The code is provider-pluggable: every Qwen-backed task has a deterministic
fallback, so the system degrades gracefully to offline rules and upgrades to Qwen
the moment `DASHSCOPE_API_KEY` is present.

## Package layout

```
due_process/
  models.py          data model (commitments, logs, ledger, violations, ...)
  corpus.py          legal grounding corpus (IDEA CFR / U.S.C. / case law)
  ledger.py          deterministic promised-vs-delivered minutes math
  materiality.py     material-failure rule + violation detection + comp estimate
  deadlines.py       2-year statute-of-limitations clock (leap-year safe, per-state)
  pwn.py             Prior Written Notice 7-element checklist (34 CFR 300.503(b))
  grounding.py       evidence-by-ID; rejects ungrounded claims
  analysis.py        the deterministic pipeline the agent calls per commitment
  agent.py           Track 4 orchestrator with human-in-the-loop checkpoints
  scenarios.py       synthetic scenarios with ground-truth labels
  llm/               bounded LLM layer (client + classification/extraction/narrative)
  instruments/       fixed cited templates + the human approval gate
  evaluation/        labeled dataset + metrics + grounded-vs-baseline runner
  examples/          runnable demos
```

## Not legal advice

This is information and drafting support, not legal advice. A human approves every
action. Legal specifics are the federal floor and must be localized and verified
against your state's special-education regulations before reliance.

See [`idea1-iep-enforcement-agent.md`](idea1-iep-enforcement-agent.md) for the full
concept, positioning, and build spec.
