# Due Process: An IEP Enforcement Agent

_Concept, positioning, and build spec. Idea 1 from the Qwen Cloud hackathon analysis. Prepared June 30, 2026._

> **Archived discovery brief.** This file preserves early product exploration and
> contains superseded market, model, privacy, and legal assumptions. It is not the
> current product specification. Use `README.md`, `docs/SUBMISSION.md`,
> `docs/architecture.md`, and `SECURITY.md` for current claims and behavior.

---

## One line

The incumbents prepare you for the IEP meeting. This one holds the school accountable after it.

A grounded compliance agent that tracks whether a school actually delivers the services it promised in a child's IEP, proves the gap when it does not, computes what the child is owed, and drafts the remedy with every claim cited to a real legal source.

---

## The problem

Millions of students receive services under IDEA through an Individualized Education Program. The legal effect and remedy depend on governing law and case-specific facts; an IEP should not be marketed simply as a private contract.

The enforcement system puts the entire burden on the parent. Private special education advocates run $150 to $250 an hour, so most families cannot afford one and go without. The result is that kids do not get what the law guarantees, and almost no one checks.

The work parents are told to do by hand is exactly what software should automate and currently does not on the parent side. The legal aid guidance is blunt: request the service logs, count delivered minutes against required minutes, and if the child consistently gets less, that is evidence rather than a feeling. A concrete example from that guidance: if the IEP requires 108 sessions and the logs show 72 delivered with 12 missed due to child absence, the school missed 24, which is grounds for a state complaint.

---

## Market reality: who already exists

Correction from the early read. The parent side is not empty. It filled in fast over the last few months. Three direct parent facing AI tools, all launched or updated between January and May 2026:

- **Undivided IEP Assistant.** The most serious. Backed by a funded startup. Extracts information from an uploaded IEP, identifies sections across district formats, flags where goals can be improved or services and accommodations added. Paid membership, pairs with human Navigators, HIPAA compliant, not trained on uploads.
- **IEP Advocate.ai.** Closest to the original concept. Upload the IEP, evaluations, and progress notes, the AI answers from the records plus state law, generates prep checklists, and drafts parent concerns and evaluation request letters. Commercial, 14 day trial.
- **IEP Compass.** Markets an AI advocate that reads the IEP, explains entitled services, prepares meeting briefings, and references Prior Written Notice and state law. Free tier plus subscription, with scholarships.

The only open source parent tool is the Burnes Center and Innovate Public Schools AIEP tool, but it is summarize and translate, not advocacy. It did catch a real error: staff said a child was entitled to 227 minutes of weekly support but wrote down 100, and the parent would not have noticed without it.

Separately there is a whole category of service tracking software, but it all sits on the school side. Euna flags under and over served students and sends overdue notifications. AbleSpace surfaces the discrepancy within days when a provider logs 50 required minutes but delivers 35. These exist to protect the district in an audit. The parent never sees that data unless they formally request the logs.

---

## The gaps

What none of the parent facing tools do. These are the openings.

1. **No longitudinal enforcement.** Every parent tool is a point in time prep assistant that helps you get ready for the annual meeting. None run across the whole year tracking whether the school delivered what the IEP promised, which is where violations actually live. The math is manual and unforgiving. Using the example above, 108 required against 72 delivered with 12 excused leaves 24 missed, and the parent is left to count that by hand and decide what it means. No parent tool computes it.

2. **No calculation of what is owed, and no deadline guard.** When a school falls short the remedy is compensatory services, and the deadline is typically within two years of the violation. A parent who arrives with three months of tracking data is in a far stronger position than one who says I think services were missed. The standard is material failure to implement, a case by case judgment about whether the gap was significant. Calculating the shortfall, applying that standard, and tracking the statute of limitations is real work none of the incumbents automate.

3. **No grounding.** The AI knows special ed law is a trust me LLM. In a context where a parent might quote a provision at a meeting, a hallucinated citation is worse than useless. None of these tools appear to link each assertion to the exact statute text plus the exact line in the IEP with a verifiable source the parent can click and check.

4. **No published accuracy, and almost no open source.** No incumbent reports precision or recall on violation detection. The claims are unfalsifiable marketing. Only the summarize and translate tool is open source.

---

## How to place it

Do not compete where the three incumbents already sit.

**Do not own:** help me understand my IEP and prepare for the meeting. Taken by Undivided, IEP Advocate.ai, and IEP Compass.

**Own instead:** the job that comes after the meeting and runs all year. Did the school deliver what they promised, and if not, prove it and get it remedied before the clock runs out.

This is a different job, at a different time, with a different technical core.

| Dimension | The incumbents | This product |
|---|---|---|
| Job | Understand the IEP, prep for the meeting | Enforce the IEP after it is signed |
| Timing | Point in time, before the annual meeting | Longitudinal, across the whole school year |
| Core artifact | Question and answer over a PDF | A compliance ledger of promised versus delivered |
| Output | Talking points and a couple of letters | Detected violations, compensatory math, a drafted complaint, all cited |
| Trust model | Trust the LLM | Every claim grounded to a verifiable source |
| Proof | Marketing claims | Published precision and recall |
| Access | Commercial or membership gated | Open source |

The positioning line to lead with everywhere, the demo, the README, the blog: from IEP review, which is crowded, to IEP enforcement, which is open.

---

## How it actually works

### System overview

A grounded compliance ledger with an agent on top. It ingests the IEP and the service logs, tracks promised minutes against delivered minutes over time, detects material failures, computes compensatory time owed as a starting position, and drafts the correct instrument with every claim cited to source. A human approves every outbound action.

The pipeline: parse the IEP into structured service commitments, ingest service logs and parent inputs, run the deterministic ledger, classify and flag violations, compute deadlines, draft the instrument, route to the parent for approval, send and timestamp.

### The Qwen and Alibaba Cloud stack (real)

Models, all via Alibaba Cloud Model Studio (console at modelstudio.console.alibabacloud.com, OpenAI and Anthropic compatible endpoints, Singapore region primary), which also satisfies the hackathon requirement to build on Qwen Cloud:

- **Qwen3.7-Max** for orchestration, reasoning, and drafting. 1M token context, agent first, strong on tool calls and long horizon workflows. Handles the agent loop and the letter narrative. Use `preserve_thinking` for multi turn agent consistency.
- **Qwen3.6-Plus** as the cheaper workhorse for routine extraction and classification, to keep token cost down on high volume steps.
- **A vision capable Qwen** (Qwen3.6 multimodal or Qwen3.7-Plus-Preview) to read scanned IEP PDFs and photographed service logs, since real documents arrive as images.
- **Qwen3.6-35B-A3B**, open weight under Apache 2.0, as the local or private VPC option for the privacy path so identifiable records never leave the parent's control. Runs on a single 24 GB GPU.
- **Prompt caching** on the long IEP context. Ingest a 50 page IEP once, query it many times, pay roughly a tenth on cached input.
- Optional **Qwen3-ASR-Flash** for voice logging so a parent can speak a missed session into the record.

Backend on Alibaba Cloud, which is what the deployment proof must show:

- **Function Compute** for the ingestion, parsing, and the deterministic ledger jobs, or **ECS / ACK** for a persistent service.
- **Object Storage Service (OSS)** for documents (IEPs, logs, drafts) with server side encryption.
- **ApsaraDB RDS for PostgreSQL** for the relational ledger, violations, and deadline clock. **Tablestore** optionally for the append only event log of service entries. **ApsaraDB for Redis** for caching.
- **API Gateway** and **Server Load Balancer** in front. A GPU **ECS** instance for the self hosted open weight model on the privacy path.
- Deployment proof for judging: a code file that invokes Model Studio and the Function Compute or ECS deployment, plus the short recording.

### Data model (real)

- **ServiceCommitment**, parsed from the IEP services page: id, service_type (e.g. speech_language, occupational_therapy), frequency_count, frequency_period (week or month), duration_minutes, setting (individual or group, pull out or push in), group_size_max, provider_qualification, linked_goal_ids, effective_start, effective_end, source_ref (IEP page and section).
- **ServiceLog**, from school logs or parent inputs: id, commitment_id, date, minutes_delivered, setting_actual, group_size_actual, provider, status (delivered, short, missed), missed_reason_text, source_ref (log page or parent email timestamp).
- **DeliveryLedger**, computed per commitment per period: required_minutes, delivered_minutes, excused_minutes, unexcused_shortfall_minutes, running totals.
- **Violation**, computed then classified: id, commitment_id, type (missed_sessions, short_sessions, group_dilution, wrong_provider, late_start, unimplemented_accommodation), window_start, window_end, shortfall_minutes, materiality (deterministic flag plus LLM rationale), evidence_refs, status (open, resolved_by_makeup, escalated).
- **DeadlineClock**: violation_id, discovery_date, sol_expiry_date (discovery plus two years, localized to state), days_remaining.
- **Instrument**, drafted: type (service_log_request, pwn_request, iee_request, state_complaint, due_process, mediation_request), violation_ids, draft_text, citations, status (draft, approved, sent), sent_timestamp.

### The deterministic and LLM boundary (real)

This is the AgentArmor split made concrete. No LLM ever does the math or the law lookup.

Deterministic code, unit tested and auditable:
- Minutes arithmetic: required versus delivered versus excused, and the running ledger.
- Materiality thresholding: a documented, configurable rule, for example flag when unexcused shortfall reaches a set percentage of required minutes over a rolling window, or a set number of consecutive missed sessions. The number is a transparent rule, not a model guess, and it cites the material failure standard as its rationale.
- Statute of limitations math: discovery date plus the statutory period, localized to the state.
- Prior Written Notice checklist: does the school's PWN contain all seven required elements under 34 C.F.R. 300.503(b).

LLM, bounded, populating fixed scaffolds:
- Classify a free text missed reason as excused (child absence, a fire drill that was made up) versus unexcused (provider absence, no substitute, scheduling conflict). Ambiguous classifications are flagged for the human, never auto resolved.
- Extract service commitments from a messy IEP, with the parsed values shown back to the parent to confirm.
- Summarize the pattern in plain language.
- Draft the letter narrative into a template whose legal scaffolding and citations are fixed by code.

Human in the loop checkpoints: confirm parsed commitments, confirm the excused or unexcused call on flagged items, approve any outbound instrument before it is sent.

### Grounding by evidence ID

The Ops Flight Recorder pattern transplanted. Every flagged violation links to three things the parent can click and verify:
1. the IEP provision by page and section,
2. the service log entry or entries that show the shortfall,
3. the governing IDEA or state regulation that defines the standard.

Hallucination is prevented by construction. The model cannot assert a legal standard that is not in the grounding corpus below, and it cannot assert a shortfall the deterministic ledger did not compute.

### MCP integrations and custom skills (real)

- MCP to a calendar so service days are tracked against the IEP schedule and missed sessions are flagged in near real time.
- MCP to the document store on OSS for IEPs, logs, and drafts.
- MCP to email so logged inquiries about a missed session go out with a timestamp, which is itself evidence, and so the school's responses are captured.
- Custom Qwen skills, one per instrument: service log request, PWN request, IEE request, state complaint, each a fixed legal template the model fills rather than free composes.

---

## Legal grounding corpus (real)

This is the backbone of the grounding layer. The agent grounds every legal claim to one of these. The CFR sections below were verified against the eCFR and the Cornell Legal Information Institute. Federal floor only; states add their own timelines and procedures, so the corpus must be localized per state.

| Provision | Governs | How the agent uses it |
|---|---|---|
| 20 U.S.C. 1401(9); 34 C.F.R. 300.17 | Definition of FAPE | The umbrella right the whole analysis rests on |
| 20 U.S.C. 1412(a)(1) | State duty to make FAPE available | Establishes the obligation being enforced |
| 34 C.F.R. 300.320 | IEP content, including the statement of services with frequency, duration, and location | Source for parsing the service commitments |
| 34 C.F.R. 300.321 | IEP Team composition | Checking who was required at a meeting |
| 34 C.F.R. 300.323(a),(c) | IEP in effect at start of year, no delay in implementation | The core implementation duty delivery is checked against |
| 34 C.F.R. 300.324(b) | Periodic review and revision of the IEP | Timing of reviews |
| 34 C.F.R. 300.322 | Parent participation in meetings | Procedural rights |
| 34 C.F.R. 300.300 | Parental consent | Consent and revocation handling |
| 34 C.F.R. 300.502 | Independent Educational Evaluation at public expense | Instrument when the parent disputes the school evaluation |
| 34 C.F.R. 300.503 | Prior Written Notice and its seven required elements | Check the school's PWNs for compliance, and request PWN when services change |
| 34 C.F.R. 300.504 | Procedural safeguards notice | Parent rights reference |
| 34 C.F.R. 300.506 | Mediation | Lower friction dispute path |
| 34 C.F.R. 300.151 to 300.153 | State complaint procedures | Default path for service delivery shortfalls |
| 34 C.F.R. 300.507 to 300.516 | Due process complaint and hearing | Escalation path for contested cases |
| 20 U.S.C. 1415(b)(6), (f)(3)(C) | Two year statute of limitations for filing | Drives the deadline clock |
| Endrew F. v. Douglas County Sch. Dist. RE-1, 580 U.S. 386 (2017) | Substantive FAPE standard | Frames whether the program was reasonably calculated for progress |
| Van Duyn v. Baker Sch. Dist., 502 F.3d 811 (9th Cir. 2007) | Material failure to implement standard | Basis for the materiality threshold rule |
| Reid v. District of Columbia, 401 F.3d 516 (D.C. Cir. 2005) | Compensatory education as a flexible equitable remedy | Why comp time is an estimated starting position, not a mechanical entitlement |

Important real nuance the product must respect: compensatory education is equitable and fact specific, not an automatic hour for hour formula. The agent computes a defensible starting number and labels it as such.

---

## Worked example (real numbers, real citations)

The IEP specifies speech and language therapy, three sessions per week, thirty minutes each, individual pull out, under 34 C.F.R. 300.320. Over a thirty six week school year that is 108 sessions, or 3,240 minutes.

The agent ingests the service logs. They show 72 sessions delivered. Twelve of the missed sessions were on days the child was absent. The agent classifies those twelve as excused and the remaining 24 as unexcused, because the logged reasons are provider absence and no substitute.

Deterministic ledger: 108 required, 72 delivered, 12 excused, 24 unexcused shortfall, which is 720 minutes, or 22 percent of the year.

Materiality rule fires because unexcused shortfall crosses the configured threshold over the window, which maps to the material failure standard in Van Duyn. The agent does not assert the school broke the law on its own authority. It states the computed shortfall, links the 24 log entries, links the IEP service line, and links 34 C.F.R. 300.323 as the implementation duty and Van Duyn as the standard.

Compensatory estimate: 720 minutes as a starting position, flagged as equitable and subject to the Reid analysis rather than guaranteed.

Deadline clock: discovery date plus two years under 20 U.S.C. 1415, localized to the state, with days remaining shown.

Instrument: the agent drafts a service log request first if logs are incomplete, then a state complaint under 34 C.F.R. 300.151 to 300.153, citing the specific IEP provision by page, the 24 log entries, and the governing standard, with the compensatory ask framed as equitable. The parent reviews and approves before anything is sent.

---

## Evaluation (real design)

This single move beats every incumbent's unfalsifiable marketing and fixes the aggregate metrics gap.

- **Dataset.** Synthetic IEP and log pairs across service types and shortfall patterns with known ground truth, plus a small set of de-identified real IEPs with PII redacted and outcomes labeled by a special education advocate or attorney if one can be recruited.
- **Labels** per commitment and window: material_failure as yes or no, comp_minutes_owed as a range since the remedy is equitable, and the correct instrument.
- **Metrics.** Precision, recall, and F1 on material failure detection. Within range accuracy or mean absolute error on compensatory minutes. Citation accuracy, the percent of cited provisions that are correct, on point, and verifiable against the eCFR. False positive rate on violation flags, which is the number that matters most, because telling a parent they have a case when they do not is the worst failure.
- **Baseline.** Raw Qwen3.7-Max prompted to find IEP violations and cite the law, with no deterministic ledger and no grounding corpus. Show the grounded system's citation accuracy and false positive rate beating it. That contrast is the credibility story.

---

## Data, privacy, and FERPA (real)

IEPs and service logs may be education records containing direct and indirect identifiers under FERPA, 20 U.S.C. 1232g and 34 C.F.R. Part 99. Treat them accordingly.

- The public demo accepts only synthetic or already-de-identified records. Automated redaction is defense in depth, not a compliance guarantee. Vision images must be redacted before cloud upload. Document authorization, retention, access, deletion, and incident response before real use.
- Encrypt at rest with OSS server side encryption and in transit. No training on user uploads. Per user isolation.
- This matches the privacy claims the incumbents make, stated concretely rather than as a slogan.

---

## Track fit

- **Track 4, Autopilot Agent.** Lean into the end to end workflow with human approval at each escalation. The Autopilot brief asks for ambiguous inputs, external tool calls, and human checkpoints at critical decisions, which this matches almost word for word.
- **Track 1, MemoryAgent.** Lean into the year long memory and forgetting story. Timely forgetting means a resolved deficit drops off the active list once makeup sessions are delivered. Recalling critical memories means surfacing a months old shortfall before the statute runs.

Recommendation: Track 4 if the demo centers on the workflow and the drafted remedy, Track 1 if it centers on the longitudinal ledger and the forgetting policy.

---

## How it maps to the judging criteria

- **Technical Depth and Engineering, 30%.** The deterministic core, the grounding layer, custom skills, MCP to calendar and document store and email. Real engineering, not an LLM wrapper, which is what this axis pays for.
- **Innovation and AI Creativity, 30%.** The deterministic versus heuristic split, the evidence ID grounding, the forgetting policy. Clean modular architecture with non trivial logic.
- **Problem Value and Impact, 25%.** Authentic pain affecting millions of families, and a tool a disability rights nonprofit could adopt, which is the open source adoption signal this axis rewards.
- **Presentation and Documentation, 15%.** A demo that shows a shortfall detected, the law and the IEP line cited, the compensatory math, and the drafted complaint, with a human approving each step.

---

## Go to market lever

The incumbents target individual paying parents. The same open tool could also aim at the federally funded Parent Training and Information centers and pro bono advocates who attend meetings for free and are chronically under resourced. A different distribution path than the consumer apps, and it strengthens the open source community adoption story the Impact criterion rewards.

---

## Honest risk read

This is a more contested space than first implied, so the bar is higher than green field. But the enforcement wedge is genuinely unoccupied, more defensible than a generic IEP helper, and fits the grounding and evaluation signature better than anything else in the five ideas. The contest is winnable precisely because the hard parts, deterministic tracking, grounded evidence, deadline math, are things most hackathon entries will not bother to build.

One framing caution: keep it information and drafting support, not legal advice, with a human approving every action. That framing is honest, it manages the legal exposure, and it showcases the human in the loop design rather than hiding it.

---

## Hackathon scope cut (what is real in nine days)

- One state's procedural pathway, the federal floor for the rest.
- Two or three service types, speech, OT, PT, where the minutes model is cleanest.
- One common IEP format for parsing, with the manual confirm step covering format drift.
- Synthetic logs with an injected shortfall plus one or two de-identified real IEPs for the demo.
- Instruments: service log request and a state complaint draft, the two highest leverage, plus the PWN compliance check. Defer due process and IEE drafting to the roadmap.
- Eval: the synthetic set precision, recall, and false positive rate plus citation accuracy against the raw LLM baseline. Even small beats the incumbents' zero.

---

## Build sequence

1. **Stand up Alibaba Cloud first.** Apply for the hackathon credits coupon, get a minimal Qwen backend running on Model Studio plus Function Compute, and capture the deployment proof recording before any features. This requirement filters out most of the field.
2. **Build the deterministic core.** Minutes math, materiality rule, the deadline engine, the PWN checklist. The hard center, and it does not depend on the LLM.
3. **Add grounding.** Wire every claim to its three sources and load the legal corpus.
4. **Add the LLM layer, bounded.** Commitment extraction with confirm, excused versus unexcused classification with flagging, plain language summaries.
5. **Add drafting with human in the loop.** Service log request and state complaint, gated behind parent approval.
6. **Produce the eval.** The synthetic set with a reported false positive rate and citation accuracy.
7. **Record the demo around the wedge.** Shortfall detected, sources cited, math shown, complaint drafted, human approving.
8. **Write the optional blog post.** Extra prize and doubles as documentation.

---

## Sources and key facts

- IDEA regulations verified this session against the eCFR (ecfr.gov) and the Cornell Legal Information Institute (law.cornell.edu): 34 C.F.R. 300.320, 300.321, 300.322, 300.323, 300.324, 300.502, 300.503, 300.504, 300.506, and the 300.507 to 300.516 due process subpart. Authority cite 20 U.S.C. 1221e-3, 1406, 1411 to 1419, 3474.
- Statutory and case citations from established special education law, to be confirmed against primary sources and localized per state before reliance: FAPE 20 U.S.C. 1401(9) and 1412(a)(1); state complaint 34 C.F.R. 300.151 to 300.153; two year limitations 20 U.S.C. 1415(b)(6) and (f)(3)(C); Endrew F. v. Douglas County (2017); Van Duyn v. Baker Sch. Dist. (9th Cir. 2007); Reid v. District of Columbia (D.C. Cir. 2005); FERPA 20 U.S.C. 1232g and 34 C.F.R. Part 99.
- Early secondary-source market/legal notes in this archived brief must not be used as current product claims; verify current statistics and legal propositions against primary sources.
- Parent facing tools, Undivided, IEP Advocate.ai, IEP Compass, and the AIEP summarize and translate tool with the 227 versus 100 minutes catch: vendor sites, The Frisc, and Reboot Democracy.
- School side service tracking, Euna, AbleSpace, Brolly: vendor sites and Level Data.
- Qwen models and Alibaba Cloud Model Studio, model lineup, context windows, prompt caching, the open weight Qwen3.6-35B-A3B, and the Singapore compatible endpoint: Qwen official blog, OpenRouter model listing, and 2026 model writeups.
- Hackathon tracks, prizes, judging criteria, and requirements: Devpost listing for the Global AI Hackathon Series with Qwen Cloud.

_This brief is strategic and technical analysis, not legal advice. Verify current product features, model availability, and all legal specifics against primary sources and your state's special education regulations before relying on them._
