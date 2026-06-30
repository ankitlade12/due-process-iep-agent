"""Tests for the Track 4 agent orchestrator (offline, no key)."""

from datetime import date, datetime

from due_process.agent import (
    ApprovalPolicy,
    AutoApprovePolicy,
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


def test_autopilot_full_run_drafts_and_sends():
    run = _run(AutoApprovePolicy())
    # Extracted the single speech commitment from IEP text.
    assert len(run.commitments) == 1
    # Clear reasons -> nothing ambiguous -> no human needed.
    assert run.classification.needs_human_count == 0
    # Deterministic analysis flagged the material failure.
    assert run.analyses[0].materiality.is_material is True
    # A complaint was drafted, approved, and sent.
    complaint = next(i for i in run.instruments
                     if i.type.value == "state_complaint")
    assert complaint.status == InstrumentStatus.SENT
    assert complaint.sent_timestamp == NOW
    assert run.needs_human is False
    assert run.audit  # audit trail recorded


def test_manual_policy_stops_at_commitment_confirmation():
    run = _run(ApprovalPolicy())  # default: approves nothing
    assert run.needs_human is True
    # Stopped before analysis/drafting.
    assert run.analyses == []
    assert run.instruments == []


def test_ambiguous_reason_blocks_auto_send_but_still_analyzes():
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


def test_instruments_sent_only_after_approval():
    run = _run(AutoApprovePolicy())
    for inst in run.instruments:
        # Auto-approve sends them; status reflects an explicit approval gate.
        assert inst.status == InstrumentStatus.SENT
