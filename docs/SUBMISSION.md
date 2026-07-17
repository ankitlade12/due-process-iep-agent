# Devpost submission — Due Process

**Track:** 4, Autopilot Agent

**Built with:** Qwen Cloud Model Studio and Alibaba Cloud Function Compute

## Elevator pitch

Due Process turns an IEP service schedule and messy delivery logs into an
auditable review: what was promised, what the records show, which source rows
support each concern, and a human-review evidence packet. Qwen handles ambiguous
language; deterministic code handles minutes, thresholds, deadlines, grounding,
and approval state.

## The problem

IEP delivery evidence is scattered across plans, provider logs, emails, and
calendars. Families and under-resourced advocates must manually reconstruct the
record while deadlines continue to run. Existing tools increasingly support IEP
review, service tracking, and letter drafting. Our wedge is not an unsupported
“only product” claim: it is an open, provenance-first workflow whose calculations
and publication gates can be inspected and reproduced.

## What it does

1. Extracts frequency, duration, setting, and service type from redacted IEP text.
2. Classifies free-text missed-session reasons; ambiguous cases stop for a human.
3. Computes required, delivered, excused, and unexcused minutes deterministically.
4. Applies a configurable **review policy**, not a legal bright-line test.
5. Estimates compensatory minutes as a discussion starting point, not an award.
6. Computes federal-floor deadline indicators and warns that state rules vary.
7. Publishes only claims tied to IEP text, log IDs, and controlled corpus IDs.
8. Creates a draft packet and waits for human approval before external storage.
9. With authorized multi-case data, privacy-gates de-identified pattern review.

## Why it is a strong Track 4 agent

- **End-to-end workflow:** ingest → interpret → calculate → ground → draft →
  approve → optional OSS artifact.
- **Ambiguous inputs:** Qwen extracts service commitments and interprets narrative
  absence reasons, with local fallbacks and explicit fallback provenance.
- **Real external tool:** an authenticated Function Compute request can store a
  content-addressed evidence packet in Alibaba OSS only after
  `approval.store_evidence_packet=true`.
- **Human checkpoints:** parsed commitments, ambiguity, and external action are
  separate gates.
- **Production signals:** request bounds, authentication for real cases, generated
  request IDs, hashes and receipts, audit entries, offline tests, and CI.

## Technical boundary

| Qwen Cloud | Deterministic application code |
|---|---|
| Extract commitments from messy text | Ledger arithmetic |
| Classify narrative reasons | Configurable review threshold |
| Fill narrative scaffolds | Deadline calculation |
| Read attested redacted/synthetic images | Citation and evidence-ID validation |

The Function Compute response reports successful and failed Qwen calls, task
methods, request IDs when available, latency, and fallback reasons. Having a key
configured is never presented as proof that Qwen completed the task.

## Reproducible evaluation

`python -m due_process.evaluation.run_eval --offline`

| metric | grounded | offline heuristic baseline |
|---|---:|---:|
| precision | 1.00 | 0.78 |
| recall | 1.00 | 1.00 |
| false-positive rate | 0.00 | 0.50 |
| citation-ID accuracy | 1.00 | 0.00 |
| compensatory-minutes MAE | 0.0 | n/a |

This is an 11-case engineering evaluation: seven positive labels, four negative,
and two independently documented/court-derived cases. Most labels are synthetic
and encode the product's review policy. It tests consistency and provenance, not
legal validity, real-world accuracy, or case outcomes. `--online` is a separate,
variable raw-Qwen comparison.

## Safety and privacy

- Public demo: synthetic or already-de-identified records only.
- Text redaction reduces direct identifiers but is not a FERPA guarantee.
- Vision requires an explicit redacted/synthetic attestation before upload.
- Empty public API calls run only a synthetic example; custom cases require a
  Bearer token.
- Drafts are information and drafting support, not legal advice.
- The 15%/three-consecutive-session policy is a configurable review signal.
- Cross-case analysis requires authorization and does not determine liability or
  guarantee a remedy.

## What we learned

The credible AI story is not “let the model decide.” It is designing a boundary
where a model is useful on language while every consequential number and published
claim remains inspectable. The second lesson is that provenance must describe what
actually happened: a fallback is a valid safe result, but it cannot be labeled as
a successful model result.

## What is next

- Advocate-labeled, de-identified validation under an approved data protocol.
- State-specific modules reviewed by qualified local experts.
- Short-lived cloud identities/RAM roles instead of long-lived OSS keys.
- Accessibility and adversarial privacy testing.
- Calendar/email connectors behind the same explicit approval contract.

## Three-minute demo

**0:00–0:20 — Problem.** Show a redacted IEP promise and a messy service-log CSV.
“The hard part is not reading one document. It is reconstructing a defensible
record across months.”

**0:20–0:55 — Live input.** In the case desk, choose **Upload redacted case**, paste
the service line, upload the sample CSV, and run the live Qwen review. Correct one
extracted field, confirm it, and resolve one deliberately ambiguous log reason.

**0:55–1:25 — Boundary.** Show actual Qwen call provenance beside the deterministic
ledger. Point out any fallback honestly. Say: “Qwen interprets language; it never
does this arithmetic or chooses a citation.”

**1:25–1:55 — Evidence.** Open a finding and show its IEP excerpt, exact log IDs,
controlled authorities, and downloadable packet. Call the threshold a review
signal, not a legal conclusion.

**1:55–2:20 — Human/external action.** Review the generated packet, click the
separate storage approval, and show the live Function Compute response containing
the OSS URI, SHA-256 receipt, request ID, and audit event.

**2:20–2:40 — Evaluation.** Run the offline benchmark and state its limitations in
one sentence.

**2:40–3:00 — Proof and close.** Show Function Compute in Alibaba Workbench, the
public repository, architecture, and passing CI. “Receipts over rhetoric: a
reproducible record, bounded AI, and a human in control.”
