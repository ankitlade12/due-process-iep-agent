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

## The core design principle: deterministic core, bounded LLM

The thing that makes this credible (and not "trust the LLM") is a hard boundary:

| **Deterministic code** (unit-tested, auditable) | **LLM** (bounded, fills fixed scaffolds) |
|---|---|
| Minutes arithmetic: required vs delivered vs excused | Classify a free-text missed reason as excused / unexcused |
| Materiality threshold (the *material failure* standard) | Extract service commitments from a messy IEP |
| Statute-of-limitations math | Summarize the pattern in plain language |
| Prior Written Notice 7-element checklist | Draft the letter narrative into a fixed legal template |

**No LLM ever does the math or the law lookup.** Every flagged violation is grounded
to three things a parent can click and verify: the IEP provision, the service-log
entries that show the shortfall, and the governing IDEA/state regulation.

## Status

Early build. Implemented so far (no cloud or API key required):

- `due_process.models` — the full data model (commitments, logs, ledger, violations, deadlines, instruments)
- `due_process.corpus` — the legal grounding corpus (CFR / U.S.C. / case law) every claim cites
- `due_process.ledger` — deterministic promised-vs-delivered minutes math
- `due_process.materiality` — the configurable material-failure rule + violation classification
- `due_process.deadlines` — the 2-year statute-of-limitations clock, localized per state
- `due_process.pwn` — the Prior Written Notice 7-element compliance checklist (34 CFR 300.503(b))
- `due_process.grounding` — the evidence-by-ID layer that ties every claim to its sources

Coming next: the bounded LLM layer (Qwen via Alibaba Cloud Model Studio), instrument
drafting with human-in-the-loop approval, and the published precision/recall eval.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Reproduce the worked example from the spec (108 required vs 72 delivered sessions):
python -m due_process.examples.worked_example

# Run the deterministic-core test suite:
pytest
```

## Not legal advice

This is information and drafting support, not legal advice. A human approves every
action. Legal specifics are the federal floor and must be localized and verified
against your state's special-education regulations before reliance.

See [`idea1-iep-enforcement-agent.md`](idea1-iep-enforcement-agent.md) for the full
concept, positioning, and build spec.
