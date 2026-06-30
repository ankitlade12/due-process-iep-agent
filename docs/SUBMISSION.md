# Devpost submission — Due Process

**Track:** Autopilot Agent · **Built on:** Qwen Cloud (Model Studio)

---

## Elevator pitch

The incumbents prepare you for the IEP meeting. **Due Process holds the school
accountable *after* it** — a grounded agent that tracks whether a school delivered
the special-education services it legally promised, proves the gap, computes what
the child is owed, and drafts the cited remedy, with a human approving every step.

## Inspiration

Over 8 million US students have a legal right under IDEA to specific services
written into an IEP — a binding contract. Schools routinely under-deliver, and the
entire enforcement burden falls on parents, who mostly can't afford the $150–250/hr
advocates. A wave of AI tools launched in 2026 to help parents *prep for the
meeting* — but none of them do the job that comes *after*: checking, all year,
whether the school actually delivered, and proving it when it didn't. That job is
unoccupied, and it's exactly what software should automate.

## What it does

Give it the IEP and the service logs. It:

1. **Extracts** the promised services (frequency × duration × setting).
2. **Classifies** each missed session's reason as excused (child absence) vs.
   unexcused (the school failed to staff it) — flagging anything ambiguous for a
   human.
3. **Computes** the promised-vs-delivered minutes ledger deterministically.
4. **Detects** a *material failure to implement* using a transparent, configurable
   rule grounded in the Van Duyn standard.
5. **Estimates** the compensatory time owed (as an equitable starting position per
   Reid v. District of Columbia — not a mechanical formula).
6. **Tracks** the 2-year statute-of-limitations deadline.
7. **Drafts** the right instrument — a service-log request or a state complaint —
   with every claim cited to the IEP line, the log entries, and the governing law.
8. **Waits for a human** to approve before anything is sent.

## Why it's novel — and who it actually helps

This isn't another paid consumer app. It's open infrastructure for the people who
already help families for free:

- **Enforcement, not prep** — the only tool that checks, all year, whether the
  school *delivered*, not just one that preps you for the meeting.
- **Systemic evidence** — it aggregates shortfalls across many families (with
  k-anonymity) into a *systemic* state complaint (34 C.F.R. 300.151(b)), forcing
  district-wide relief that fixes services for **every** affected child. In the
  demo, 12 students → one de-identified finding (58% with a material failure,
  6,930 minutes owed) → a district complaint, with no child identified.
- **A force-multiplier for the under-resourced** — Parent Training & Information
  centers and pro-bono advocates are swamped and have no tooling; this is the open
  backbone that 10×'s them, handling a whole caseload at once.
- **Built for access** — "receipts, not lawsuits," and the parent-facing summary
  translates via Qwen, because the enforcement system silently assumes an
  English-fluent, sophisticated parent and most families aren't.

## How we built it — the one idea that makes it credible

A hard boundary: **no LLM ever does the math or the law lookup.**

- **Deterministic core** (unit-tested): the minutes ledger, the materiality rule,
  the statute-of-limitations clock, the Prior Written Notice checklist.
- **Bounded Qwen LLM**: only the messy-language tasks — extract commitments,
  classify reasons, write the letter narrative — each filling a fixed scaffold.
- **Grounding**: every violation links to three verifiable sources, and every
  citation is validated against a legal corpus, so a hallucinated cite is
  impossible *by construction*.
- **Human-in-the-loop**: confirm parsed values, resolve ambiguous calls, approve
  every send.

## Qwen Cloud usage

The bounded LLM layer runs on Qwen Cloud's OpenAI-compatible Model Studio endpoint:

- **`qwen3.7-max`** — the agent's reasoning and the complaint narrative
- **`qwen3.7-plus`** — the cheap workhorse for extraction and reason classification
  (JSON-structured output), and multimodal reading of scanned IEP PDFs
- Reason-deduplication and the deterministic fallbacks keep token use minimal

The agent is deployed to **Alibaba Cloud Function Compute**; the deployed function
invokes Model Studio on every request (see `deploy/`).

## How we measured it — the credibility story

Every incumbent's accuracy claim is unfalsifiable marketing. We ship a labeled eval
and report the numbers, including the one that matters most — the false-positive
rate (telling a parent they have a case when they don't):

| metric | **grounded** | raw-Qwen baseline |
|---|---|---|
| precision | 1.00 | 0.67 |
| recall | 1.00 | 0.67 |
| false-positive rate | **0.00** | 0.50 |
| citation accuracy | **1.00** | 0.52 |
| compensatory-minutes MAE | **0.0** | n/a |

The grounded system never emits an unverifiable citation and never over-flags;
the baseline (raw Qwen with no ledger and no corpus) does both — it *misses* a
third of real violations, *over-flags* half the compliant ones, and cites real,
on-point law only about half the time. (Honest caveat:
the synthetic labels track our own materiality rule, so this shows consistency and
the baseline contrast — not that the threshold is the legally correct line. Real
validation needs advocate-labeled IEPs, which is on the roadmap.)

## Challenges

- Designing the deterministic/LLM boundary so the LLM is genuinely bounded — it
  populates scaffolds but never decides materiality or authors a citation.
- Making every legal claim verifiable: the corpus + evidence-by-ID layer rejects
  any violation that isn't tied to a real provision and real log entries.
- Keeping the whole thing runnable and testable offline so the deterministic core
  stands on its own, then layering Qwen on top.

## Accomplishments

- A working end-to-end Track 4 agent with a human checkpoint at every critical
  decision and a full audit trail.
- 84 passing tests; the deterministic core reproduces a real worked example exactly
  (108 required vs 72 delivered → a 720-minute, 22% shortfall).
- A published eval — the thing no incumbent reports.

## What's next

- Advocate-labeled de-identified IEPs for a real precision/recall validation.
- More states' procedural pathways beyond the federal floor.
- MCP integrations: calendar (track sessions in near-real-time), email (timestamped
  inquiries as evidence), document store on OSS.
- Due-process and IEE drafting; the self-hosted open-weight Qwen privacy path.

## Built with

Python · Qwen Cloud (Model Studio: qwen3.7-max, qwen3.7-plus) · Alibaba Cloud
Function Compute · OpenAI-compatible SDK · Apache-2.0, fully open source.

---

# 3-minute demo video script

**0:00–0:20 — The hook.**
"8 million US kids have a legal right to special-education services written into an
IEP. Schools routinely under-deliver — and proving it is on the parent. Advocates
cost $200 an hour. Due Process is the advocate that runs all year."

**0:20–0:45 — The wedge.**
Show the positioning line: "From IEP review, which is crowded, to IEP enforcement,
which is open." One sentence: every other AI tool preps you for the meeting; this
one checks whether the school delivered after it.

**0:45–1:45 — Live demo (the core).**
Run `python -m due_process.examples.agent_demo`. Narrate the audit trail as it
prints: Qwen extracts the service from the IEP → classifies each missed reason →
the **deterministic** ledger computes 720 minutes (22%) unexcused → it's a material
failure → 12 hours of comp owed → deadline 679 days out. Then scroll the drafted
state complaint: point at the citations and the 24 linked log entries. Say: "Every
number came from code, not the model. Every citation is validated." Then run
`python -m due_process.examples.systemic_demo`: "Now multiply it — 12 families
collapse into one district-wide complaint, no child named. That's the move that
fixes it for everyone, not one kid at a time." Show the Spanish parent receipt:
"and it speaks the family's language."

**1:45–2:15 — The boundary + grounding.**
Show the README table: deterministic core vs. bounded Qwen. Emphasize: the LLM
never does math or law; a hallucinated citation is impossible by construction; a
human approves the send.

**2:15–2:40 — The eval.**
Run `python -m due_process.evaluation.run_eval`. Point at false-positive rate 0.00
and citation accuracy 1.00 vs. the raw-Qwen baseline. "No incumbent reports this."

**2:40–3:00 — Deployment + close.**
Show `deploy/` and the Function Compute response with `"llm": "qwen-online"`.
Close: "Grounded. Deterministic where it must be. Open source. Due Process —
holding schools to the contract they signed."
