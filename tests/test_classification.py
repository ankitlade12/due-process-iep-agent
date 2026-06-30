"""Tests for the excused/unexcused classifier (offline rule-based path)."""

from datetime import date

from due_process.llm.classification import classify_logs, classify_reason
from due_process.models import ExcusedClass, LogStatus, ServiceLog


def test_provider_absence_is_unexcused():
    rc = classify_reason("Provider absent, no substitute available")
    assert rc.excused == ExcusedClass.UNEXCUSED
    assert rc.needs_human is False


def test_student_absence_is_excused():
    rc = classify_reason("Student was absent (out sick)")
    assert rc.excused == ExcusedClass.EXCUSED
    assert rc.needs_human is False


def test_empty_reason_is_ambiguous():
    rc = classify_reason("")
    assert rc.excused == ExcusedClass.AMBIGUOUS
    assert rc.needs_human is True


def test_vague_reason_is_ambiguous():
    rc = classify_reason("cancelled")
    assert rc.excused == ExcusedClass.AMBIGUOUS
    assert rc.needs_human is True


def test_conflicting_reason_is_ambiguous():
    rc = classify_reason("provider was out and the student was also sick")
    assert rc.excused == ExcusedClass.AMBIGUOUS
    assert rc.needs_human is True


def _missed(idx, reason):
    return ServiceLog(id=f"l{idx}", commitment_id="c1", date=date(2025, 9, idx),
                      minutes_delivered=0, status=LogStatus.MISSED,
                      missed_reason_text=reason)


def test_classify_logs_sets_clear_and_flags_ambiguous():
    logs = [
        _missed(1, "Provider absent, no sub"),     # unexcused
        _missed(2, "Student absent"),              # excused
        _missed(3, "see notes"),                   # ambiguous
        ServiceLog(id="d", commitment_id="c1", date=date(2025, 9, 4),
                   minutes_delivered=30, status=LogStatus.DELIVERED),  # skipped
    ]
    outcome = classify_logs(logs)
    assert logs[0].excused == ExcusedClass.UNEXCUSED
    assert logs[1].excused == ExcusedClass.EXCUSED
    assert logs[2].excused == ExcusedClass.AMBIGUOUS
    assert outcome.needs_human_count == 1
    assert logs[2] in outcome.review_items


def test_delivered_logs_not_classified():
    logs = [ServiceLog(id="d", commitment_id="c1", date=date(2025, 9, 1),
                       minutes_delivered=30, status=LogStatus.DELIVERED)]
    outcome = classify_logs(logs)
    assert outcome.needs_human_count == 0
    assert "d" not in outcome.classifications
