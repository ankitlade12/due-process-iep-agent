"""Tests for the Track 4 agent orchestrator (offline, no key)."""

from datetime import date, datetime

from due_process.agent import (
    ApprovalPolicy,
    AutoApprovePolicy,
    prepare_enforcement_inputs,
    run_enforcement,
)
from due_process.instruments.drafter import LetterContext
from due_process.models import ExcusedClass, InstrumentStatus, LogStatus, ServiceLog
from due_process.scenarios import worked_example_speech

NOW = datetime(2026, 6, 30, 9, 0, 0)


def _run(policy, scenario=None):
    s = scenario or worked_example_speech(classified=False)
    return run_enforcement(
        s.logs,
        now=NOW,
        context=LetterContext(student_name="A. Doe", letter_date=NOW.date()),
        window_start=s.window_start,
        window_end=s.window_end,
        iep_text=s.iep_text,
        instructional_periods=s.instructional_periods,
        discovery_date=s.discovery_date,
        client=None,  # force offline rule-based path
        policy=policy,
    )


def test_autopilot_full_run_drafts_and_approves():
    run = _run(AutoApprovePolicy())
    # Extracted the single speech commitment from IEP text.
    assert len(run.commitments) == 1
    assert run.commitments[0].source_ref.uri == "input://iep-services-text"
    # Clear reasons -> nothing ambiguous -> no human needed.
    assert run.classification.needs_human_count == 0
    # Deterministic analysis flagged the material failure.
    assert run.analyses[0].materiality.is_material is True
    # A complaint was drafted and approved, but no delivery is simulated.
    complaint = next(i for i in run.instruments
                     if i.type.value == "state_complaint")
    assert complaint.status == InstrumentStatus.APPROVED
    assert complaint.sent_timestamp is None
    assert run.needs_human is False
    assert run.audit  # audit trail recorded


def test_manual_policy_stops_at_commitment_confirmation():
    run = _run(ApprovalPolicy())  # default: approves nothing
    assert run.needs_human is True
    # Stopped before analysis/drafting.
    assert run.analyses == []
    assert run.instruments == []


def test_ambiguous_reason_blocks_completion_but_still_analyzes():
    # One missed session with an unclassifiable reason -> stays pending.
    s = worked_example_speech(classified=False)
    s.logs.append(ServiceLog(
        id="amb", commitment_id=s.commitment.id, date=s.window_start,
        minutes_delivered=0, status=LogStatus.MISSED,
        missed_reason_text="see notes", excused=ExcusedClass.UNCLASSIFIED))
    run = _run(AutoApprovePolicy(), scenario=s)
    # Auto-approve never resolves ambiguous reasons.
    assert run.needs_human is True
    assert run.classification.needs_human_count == 1
    # Analysis still ran (the ambiguous minute is just held out).
    assert run.analyses


def test_auto_approval_does_not_claim_external_delivery():
    run = _run(AutoApprovePolicy())
    for inst in run.instruments:
        assert inst.status == InstrumentStatus.APPROVED
        assert inst.sent_timestamp is None


class _ConfirmOnlyPolicy(ApprovalPolicy):
    def confirm_commitments(self, extracted):
        return True


class _ResolvePolicy(_ConfirmOnlyPolicy):
    def __init__(self, decisions):
        self.decisions = decisions

    def resolve_ambiguous(self, items):
        return self.decisions


def test_prepared_inputs_block_analysis_until_ambiguity_is_resolved():
    scenario = worked_example_speech(classified=False)
    ambiguous = next(
        log for log in scenario.logs if log.status == LogStatus.MISSED)
    ambiguous.missed_reason_text = "See provider note"
    prepared = prepare_enforcement_inputs(
        scenario.logs,
        iep_text=scenario.iep_text,
        context=LetterContext(student_name="Student A"),
        client=None,
    )
    assert prepared.classification.needs_human_count == 1

    blocked = run_enforcement(
        scenario.logs,
        now=NOW,
        context=LetterContext(student_name="Student A"),
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        iep_text=scenario.iep_text,
        instructional_periods=scenario.instructional_periods,
        policy=_ConfirmOnlyPolicy(),
        prepared_inputs=prepared,
        require_all_ambiguities_resolved=True,
    )
    assert blocked.needs_human is True
    assert blocked.analyses == []
    assert blocked.checkpoints[-1].kind == "review_ambiguous"
    assert blocked.checkpoints[-1].pending_count == 1


def test_prepared_inputs_apply_human_decision_before_analysis():
    scenario = worked_example_speech(classified=False)
    ambiguous = next(
        log for log in scenario.logs if log.status == LogStatus.MISSED)
    ambiguous.missed_reason_text = "See provider note"
    prepared = prepare_enforcement_inputs(
        scenario.logs,
        iep_text=scenario.iep_text,
        context=LetterContext(student_name="Student A"),
        client=None,
    )
    run = run_enforcement(
        scenario.logs,
        now=NOW,
        context=LetterContext(student_name="Student A"),
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        iep_text=scenario.iep_text,
        instructional_periods=scenario.instructional_periods,
        policy=_ResolvePolicy({ambiguous.id: ExcusedClass.UNEXCUSED}),
        prepared_inputs=prepared,
        require_all_ambiguities_resolved=True,
    )
    assert run.analyses
    assert ambiguous.excused == ExcusedClass.UNEXCUSED
    review_checkpoint = next(
        item for item in run.checkpoints if item.kind == "review_ambiguous")
    assert review_checkpoint.resolved is True
    assert review_checkpoint.pending_count == 0
