"""The enforcement agent orchestrator (Track 4: Autopilot Agent).

Runs the end-to-end workflow with a human checkpoint at every critical decision:

    ingest IEP text + raw logs
      -> extract service commitments        [checkpoint: confirm parsed values]
      -> classify missed-session reasons     [checkpoint: review ambiguous]
      -> run the deterministic analysis      (no checkpoint — auditable math)
      -> choose & draft the right instrument
      -> approve before external action      [checkpoint: human approval]
      -> export/store through an explicit adapter

The deterministic core does the math and the law; the bounded LLM prepares inputs
and narrates outputs; and a person authorizes every outbound act. The agent never
classifies an ambiguous reason on its own and never approves an external action
without a human decision. Every step is recorded in an audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

from .analysis import CommitmentAnalysis, analyze_commitment
from .instruments.approval import approve
from .instruments.drafter import (
    LetterContext,
    draft_service_log_request,
    draft_state_complaint,
)
from .llm.classification import ClassificationOutcome, classify_logs
from .llm.client import LLMClient
from .llm.extraction import ExtractedCommitment, extract_commitments
from .materiality import DEFAULT_CONFIG, MaterialityConfig
from .models import (
    ExcusedClass,
    Instrument,
    ServiceCommitment,
    ServiceLog,
)
from .privacy import Redactor


# --------------------------------------------------------------------------- #
# Human-in-the-loop policy
# --------------------------------------------------------------------------- #
class ApprovalPolicy:
    """How the agent obtains human decisions at each checkpoint.

    The default pauses at every checkpoint (approves nothing), so a default run
    drafts but never authorizes external action. Subclasses supply real decisions.
    """

    name = "manual"

    def confirm_commitments(
        self, extracted: Sequence[ExtractedCommitment]
    ) -> bool:
        return False

    def resolve_ambiguous(
        self, items: Sequence[ServiceLog]
    ) -> Dict[str, ExcusedClass]:
        """Return log_id -> resolved label for items the human decided.

        Items left out stay AMBIGUOUS and are held out of the actionable
        shortfall. Ambiguous reasons are never auto-resolved.
        """
        return {}

    def approve_instrument(self, instrument: Instrument) -> bool:
        return False


class AutoApprovePolicy(ApprovalPolicy):
    """Demo/eval policy: confirms parsed commitments and approves instruments.

    Approval changes only the instrument state. It does not claim that an email,
    filing, or other transmission occurred; those require a separate adapter.
    Ambiguous reasons still remain pending.
    """

    name = "auto-approve (demo)"

    def confirm_commitments(self, extracted): return True

    def approve_instrument(self, instrument): return True


# --------------------------------------------------------------------------- #
# Audit trail + run result
# --------------------------------------------------------------------------- #
@dataclass
class AuditEntry:
    step: str
    detail: str
    at: Optional[datetime] = None


@dataclass
class Checkpoint:
    kind: str          # confirm_commitments | review_ambiguous | approve_instrument
    description: str
    resolved: bool
    pending_count: int = 0


@dataclass
class AgentRun:
    commitments: List[ServiceCommitment] = field(default_factory=list)
    extracted: List[ExtractedCommitment] = field(default_factory=list)
    classification: Optional[ClassificationOutcome] = None
    analyses: List[CommitmentAnalysis] = field(default_factory=list)
    instruments: List[Instrument] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    audit: List[AuditEntry] = field(default_factory=list)
    needs_human: bool = False

    def audit_lines(self) -> List[str]:
        return [f"[{e.step}] {e.detail}" for e in self.audit]


@dataclass
class PreparedEnforcementInputs:
    """Language-task results awaiting explicit human confirmation.

    Preparing and executing are separate so a UI can show/edit Qwen's parsed
    commitment and resolve ambiguous reasons before deterministic analysis.
    The same objects are then consumed by :func:`run_enforcement`; no model call
    is silently repeated after the human decision.
    """

    extracted: List[ExtractedCommitment] = field(default_factory=list)
    classification: ClassificationOutcome = field(
        default_factory=ClassificationOutcome)


def _redactor_for_context(
    context: LetterContext, *, redact: bool
) -> Optional[Redactor]:
    if not redact:
        return None
    extra_identifiers = {
        value: label
        for value, label in (
            (context.parent_address, "[PARENT_ADDRESS]"),
            (context.parent_contact, "[PARENT_CONTACT]"),
            (context.student_address, "[STUDENT_ADDRESS]"),
            (context.school_address, "[SCHOOL_ADDRESS]"),
        )
        if value and not value.startswith("[")
    }
    return Redactor.for_case(
        student_name=context.student_name,
        parent_name=context.parent_name,
        extra=extra_identifiers,
    )


def prepare_enforcement_inputs(
    logs: List[ServiceLog],
    *,
    iep_text: str,
    context: LetterContext,
    client: Optional[LLMClient] = None,
    redact: bool = True,
    source_uri: str = "input://iep-services-text",
) -> PreparedEnforcementInputs:
    """Run only bounded language tasks, stopping before consequential analysis."""
    redactor = _redactor_for_context(context, redact=redact)
    extracted = extract_commitments(
        iep_text, client=client,
        source_uri=source_uri, redactor=redactor,
    )
    classification = classify_logs(logs, client=client, redactor=redactor)
    return PreparedEnforcementInputs(
        extracted=extracted, classification=classification)


def run_enforcement(
    logs: List[ServiceLog],
    *,
    now: datetime,
    context: LetterContext,
    window_start: date,
    window_end: date,
    iep_text: Optional[str] = None,
    commitments: Optional[Sequence[ServiceCommitment]] = None,
    instructional_periods: Optional[int] = None,
    required_sessions_by_commitment: Optional[Dict[str, int]] = None,
    discovery_date: Optional[date] = None,
    state: str = "",
    client: Optional[LLMClient] = None,
    policy: Optional[ApprovalPolicy] = None,
    prepared_inputs: Optional[PreparedEnforcementInputs] = None,
    require_all_ambiguities_resolved: bool = False,
    config: MaterialityConfig = DEFAULT_CONFIG,
    redact: bool = True,
    source_uri: str = "input://iep-services-text",
) -> AgentRun:
    """Execute the enforcement workflow end to end.

    ``redact`` (on by default) removes known direct identifiers from text sent to
    the cloud model. This is defense in depth, not a FERPA compliance guarantee.
    """
    policy = policy or ApprovalPolicy()
    today = now.date()
    run = AgentRun()
    redactor = _redactor_for_context(context, redact=redact)

    def log_step(step: str, detail: str) -> None:
        run.audit.append(AuditEntry(step=step, detail=detail, at=now))

    # 1) Extract commitments (unless caller supplied them) ---------------------
    if commitments is None:
        run.extracted = (
            list(prepared_inputs.extracted)
            if prepared_inputs is not None
            else extract_commitments(
                iep_text or "", client=client,
                source_uri=source_uri, redactor=redactor,
            )
        )
        method = run.extracted[0].method if run.extracted else "none"
        detail = (f"Parsed {len(run.extracted)} commitment(s) from the IEP "
                  f"({method}).")
        fallback_reason = (run.extracted[0].fallback_reason
                           if run.extracted else "")
        if fallback_reason:
            detail += f" Explicit fallback reason={fallback_reason}."
        log_step("extract", detail)
        cp_ok = policy.confirm_commitments(run.extracted)
        run.checkpoints.append(Checkpoint(
            "confirm_commitments",
            "Human confirms the parsed service commitments.",
            resolved=cp_ok, pending_count=0 if cp_ok else len(run.extracted),
        ))
        if not cp_ok:
            run.needs_human = True
            log_step("checkpoint",
                     "Awaiting human confirmation of parsed commitments; "
                     "stopping.")
            return run
        commitments = [e.commitment for e in run.extracted]
        log_step("checkpoint", "Human confirmed parsed commitments.")
    run.commitments = list(commitments)

    # Reconcile logs to the confirmed commitment when the linkage is
    # unambiguous (a single service). Extraction mints fresh commitment ids, so
    # logs uploaded separately may not yet reference them.
    confirmed_ids = {c.id for c in run.commitments}
    orphans = [log for log in logs if log.commitment_id not in confirmed_ids]
    if orphans and len(run.commitments) == 1:
        target = run.commitments[0].id
        for log in orphans:
            log.commitment_id = target
        log_step("reconcile",
                 f"Associated {len(orphans)} log(s) with the confirmed "
                 f"commitment {target}.")

    # 2) Classify missed/short reasons ----------------------------------------
    run.classification = (
        prepared_inputs.classification
        if prepared_inputs is not None
        else classify_logs(logs, client=client, redactor=redactor)
    )
    methods: Dict[str, int] = {}
    for result in run.classification.classifications.values():
        methods[result.method] = methods.get(result.method, 0) + 1
    log_step("classify",
             f"Classified reasons via {methods}; "
             f"{run.classification.needs_human_count} flagged ambiguous for "
             "human review.")
    if run.classification.review_items:
        resolved = policy.resolve_ambiguous(run.classification.review_items)
        applied = 0
        applied_ids = set()
        by_id = {log.id: log for log in run.classification.review_items}
        for log_id, label in resolved.items():
            if log_id in by_id and label in (
                ExcusedClass.EXCUSED, ExcusedClass.UNEXCUSED
            ):
                by_id[log_id].excused = label
                classification = run.classification.classifications.get(log_id)
                if classification is not None:
                    classification.excused = label
                    classification.needs_human = False
                    classification.rationale = (
                        f"Human resolved as {label.value}. "
                        f"{classification.rationale}")
                applied += 1
                applied_ids.add(log_id)
        pending = len(run.classification.review_items) - applied
        run.classification.review_items = [
            log for log in run.classification.review_items
            if log.id not in applied_ids
        ]
        run.checkpoints.append(Checkpoint(
            "review_ambiguous",
            "Human resolves ambiguous excused/unexcused calls.",
            resolved=(pending == 0), pending_count=pending,
        ))
        if pending:
            run.needs_human = True
            log_step("checkpoint",
                     f"{pending} ambiguous reason(s) remain pending; held out "
                     "of the actionable shortfall.")
            if require_all_ambiguities_resolved:
                log_step(
                    "checkpoint",
                    "Analysis blocked until every ambiguous reason is resolved.")
                return run
        else:
            log_step("checkpoint", "Human resolved all ambiguous reasons.")

    # 3) Deterministic analysis per commitment --------------------------------
    for c in run.commitments:
        req = (required_sessions_by_commitment or {}).get(c.id)
        analysis = analyze_commitment(
            c, logs,
            window_start=window_start, window_end=window_end, today=today,
            required_sessions=req,
            instructional_periods=None if req else instructional_periods,
            discovery_date=discovery_date, state=state, config=config,
        )
        run.analyses.append(analysis)
        log_step("analyze",
                 f"{c.service_type.value}: "
                 f"{analysis.ledger.unexcused_shortfall_minutes} min unexcused "
                 f"shortfall, material={analysis.materiality.is_material}, "
                 f"logs_complete={analysis.ledger.logs_complete}.")

    # 4) Choose & draft the right instrument(s) -------------------------------
    incomplete = [a for a in run.analyses if a.needs_logs_first]
    if incomplete:
        inst = draft_service_log_request(
            [a.commitment for a in incomplete], context,
            window_start=window_start, window_end=window_end, client=client,
        )
        run.instruments.append(inst)
        log_step("draft", "Logs incomplete -> drafted a service-log request.")

    actionable = [a for a in run.analyses
                  if a.has_actionable_violation and not a.needs_logs_first]
    if actionable:
        inst = draft_state_complaint(actionable, context, client=client)
        run.instruments.append(inst)
        log_step("draft",
                 f"Drafted a state complaint covering "
                 f"{len(actionable)} service(s).")

    # 5) Approve each instrument (human gate) ---------------------------------
    # Approval is a state transition, not a claim of external transmission.
    # A caller may export, store, or deliver the approved artifact through a
    # separately authenticated adapter and then record the actual delivery.
    for inst in run.instruments:
        ok = policy.approve_instrument(inst)
        run.checkpoints.append(Checkpoint(
            "approve_instrument",
            f"Human approves the {inst.type.value} before external action.",
            resolved=ok,
        ))
        if ok:
            approve(inst)
            log_step(
                "approval",
                f"Human approved {inst.type.value}; ready for an authorized "
                "export, storage, or delivery adapter.",
            )
        else:
            run.needs_human = True
            log_step("checkpoint",
                     f"{inst.type.value} drafted; awaiting human approval "
                     "before external action.")

    return run
