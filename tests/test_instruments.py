"""Tests for instrument drafting and the human-in-the-loop approval gate."""

from datetime import date, datetime

import pytest

from due_process import corpus
from due_process.analysis import analyze_commitment
from due_process.instruments import (
    ApprovalError,
    LetterContext,
    approve,
    draft_pwn_request,
    draft_service_log_request,
    draft_state_complaint,
    send,
)
from due_process.models import InstrumentStatus, InstrumentType
from due_process.scenarios import incomplete_logs_speech, worked_example_speech

TODAY = date(2026, 6, 30)
NOW = datetime(2026, 6, 30, 9, 0, 0)


def _worked_analysis():
    s = worked_example_speech()
    return analyze_commitment(
        s.commitment, s.logs, window_start=s.window_start,
        window_end=s.window_end, today=TODAY,
        instructional_periods=s.instructional_periods,
        discovery_date=s.discovery_date)


def test_state_complaint_drafts_with_valid_citations():
    a = _worked_analysis()
    ctx = LetterContext(student_name="A. Doe", letter_date=TODAY)
    inst = draft_state_complaint([a], ctx)
    assert inst.type == InstrumentType.STATE_COMPLAINT
    assert inst.status == InstrumentStatus.DRAFT
    assert "State Complaint" in inst.draft_text
    assert "720" in inst.draft_text  # the comp minutes
    assert "300.151" in inst.draft_text
    corpus.validate_refs(inst.citations)  # every citation resolves


def test_service_log_request_cites_records_right():
    s = incomplete_logs_speech()
    ctx = LetterContext(letter_date=TODAY)
    inst = draft_service_log_request(
        [s.commitment], ctx, window_start=s.window_start,
        window_end=s.window_end)
    assert inst.type == InstrumentType.SERVICE_LOG_REQUEST
    assert "300.613" in inst.draft_text
    corpus.validate_refs(inst.citations)


def test_pwn_request_lists_seven_elements():
    ctx = LetterContext(letter_date=TODAY)
    inst = draft_pwn_request(ctx, proposed_change="reducing speech minutes")
    assert "300.503" in inst.draft_text
    assert "(7)" in inst.draft_text
    corpus.validate_refs(inst.citations)


def test_approval_gate_blocks_send_before_approve():
    a = _worked_analysis()
    inst = draft_state_complaint([a], LetterContext())
    with pytest.raises(ApprovalError):
        send(inst, NOW)  # not approved yet


def test_approval_then_send_records_timestamp():
    a = _worked_analysis()
    inst = draft_state_complaint([a], LetterContext())
    approve(inst)
    assert inst.status == InstrumentStatus.APPROVED
    send(inst, NOW)
    assert inst.status == InstrumentStatus.SENT
    assert inst.sent_timestamp == NOW


def test_cannot_approve_after_send():
    a = _worked_analysis()
    inst = draft_state_complaint([a], LetterContext())
    approve(inst)
    send(inst, NOW)
    with pytest.raises(ApprovalError):
        approve(inst)
