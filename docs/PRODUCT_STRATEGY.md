# Product strategy — win with the evidence flight recorder

## The sharper idea

Do not pitch “an AI special-education lawyer.” Pitch an **evidence flight recorder
for IEP service delivery**: it continuously turns promises and delivery events
into an inspectable record, catches gaps early, and prepares the next human-reviewed
step before evidence or deadlines disappear.

That framing is more defensible and more distinctive than claiming the market is
empty. Meeting-prep, service-tracking, and AI letter products already exist. The
winning combination here is:

1. open-source and advocate-facing;
2. deterministic promised-versus-delivered ledger;
3. source provenance at the row and IEP-excerpt level;
4. actual model/fallback provenance rather than “AI powered” theater;
5. approval-gated external artifacts with content hashes; and
6. authorized, privacy-gated pattern review across a caseload.

## Judge story

The memorable contrast is:

> Qwen handles ambiguity. Code handles consequences. A human controls action.

The demo should prove this rather than narrate it. One live language task, one
visible deterministic calculation, one evidence chain, one held approval, and one
Alibaba OSS receipt are enough. The hash receipt is the out-of-box moment: the
agent does not merely generate prose; it creates a verifiable case artifact.

## Initial user and workflow

Start with nonprofit parent centers, legal clinics, and pro-bono advocates—not a
fully autonomous direct-to-parent legal product. These users have repeated cases,
can review outputs, and can define safe procedures. The smallest useful workflow:

- upload redacted service language and a provider-log export;
- confirm the parsed commitment;
- reconcile the ledger and resolve ambiguous reasons;
- export a review packet;
- optionally store the approved packet with an audit receipt.

Do not expand to email sending, filing, or real cross-case data until permissions,
retention, and review protocols exist.

## Defensibility

The moat is not a prompt. It is a growing, permissioned evidence schema and
evaluation discipline:

- normalized service commitments and delivery events;
- advocate-reviewed ambiguity labels;
- state-specific, expert-reviewed procedural modules;
- source-linked outcome feedback;
- reproducible false-positive and provenance metrics; and
- transparent adapters that organizations can self-host.

## Success measures after the hackathon

Avoid vanity “letters generated” metrics. Measure:

- minutes advocates save reconstructing one record;
- percentage of extracted fields confirmed without correction;
- ambiguous classifications escalated rather than guessed;
- claims with complete IEP/log/corpus provenance;
- false-positive rate on advocate-reviewed cases;
- time from missing session to documented follow-up; and
- percentage of external artifacts with a valid approval and hash receipt.

## 30-day roadmap

1. Recruit one qualified advocate or clinic advisor and review the terminology.
2. Run five synthetic usability sessions; fix upload and evidence-navigation pain.
3. Establish a written de-identification and retention protocol before any real
   record is considered.
4. Label a small de-identified evaluation set under that protocol.
5. Build one state module only after expert review; keep the federal floor clear.
6. Add accessibility testing and a threat model before expanding the public demo.

## Explicit non-goals

- deciding whether a school violated the law;
- estimating a guaranteed legal remedy;
- replacing counsel or an advocate;
- accepting identifiable records in the public demo;
- inferring authorization for cross-family analysis; or
- sending or filing a document autonomously.
