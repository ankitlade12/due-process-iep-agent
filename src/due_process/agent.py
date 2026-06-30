"""The enforcement agent orchestrator (Track 4: Autopilot Agent).

Runs the end-to-end workflow with a human checkpoint at every critical decision:

    ingest IEP text + raw logs
      -> extract service commitments        [checkpoint: confirm parsed values]
      -> classify missed-session reasons     [checkpoint: review ambiguous]
      -> run the deterministic analysis      (no checkpoint — auditable math)
      -> choose & draft the right instrument
      -> approve before sending              [checkpoint: human approval]
      -> send (timestamped)

The deterministic core does the math and the law; the bounded LLM prepares inputs
and narrates outputs; and a person authorizes every outbound act. The agent never
classifies an ambiguous reason on its own and never sends an unapproved
instrument. Every step is recorded in an audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

from .analysis import CommitmentAnalysis, analyze_commitment
from .instruments.approval import approve, send
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
    drafts but never sends. Subclasses supply real decisions.
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
    """Demo/eval policy: confirms parsed commitments and approves instruments,
    but still refuses to auto-resolve ambiguous reasons (those stay pending)."""

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
    config: MaterialityConfig = DEFAULT_CONFIG,
    redact: bool = True,
) -> AgentRun:
    """Execute the enforcement workflow end to end.

    ``redact`` (on by default) scrubs student PII from any text sent to the cloud
    model, using the identifiers in ``context`` — FERPA-safe by default.
    """
    policy = policy or ApprovalPolicy()
    today = now.date()
    run = AgentRun()
    redactor = (Redactor.for_case(student_name=context.student_name,
                                  parent_name=context.parent_name)
                if redact else None)

    def log_step(step: str, detail: str) -> None:
        run.audit.append(AuditEntry(step=step, detail=detail, at=now))

    # 1) Extract commitments (unless caller supplied them) ---------------------
    if commitments is None:
        run.extracted = extract_commitments(
            iep_text or "", client=client,
            source_uri="oss://ieps/this-student.pdf", redactor=redactor,
        )
        method = run.extracted[0].method if run.extracted else "none"
        log_step("extract",
                 f"Parsed {len(run.extracted)} commitment(s) from the IEP "
                 f"({method}).")
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
    run.classification = classify_logs(logs, client=client, redactor=redactor)
    log_step("classify",
             f"Classified reasons; {run.classification.needs_human_count} "
             f"flagged ambiguous for human review.")
    if run.classification.review_items:
        resolved = policy.resolve_ambiguous(run.classification.review_items)
        applied = 0
        by_id = {log.id: log for log in run.classification.review_items}
        for log_id, label in resolved.items():
            if log_id in by_id and label in (
                ExcusedClass.EXCUSED, ExcusedClass.UNEXCUSED
            ):
                by_id[log_id].excused = label
                applied += 1
        pending = len(run.classification.review_items) - applied
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

    # 5) Approve & send each instrument (human gate) --------------------------
    for inst in run.instruments:
        ok = policy.approve_instrument(inst)
        run.checkpoints.append(Checkpoint(
            "approve_instrument",
            f"Human approves the {inst.type.value} before sending.",
            resolved=ok,
        ))
        if ok:
            approve(inst)
            send(inst, now)
            log_step("send", f"Human approved; sent {inst.type.value} at "
                             f"{now.isoformat()}.")
        else:
            run.needs_human = True
            log_step("checkpoint",
                     f"{inst.type.value} drafted; awaiting human approval "
                     "before sending.")

    return run
