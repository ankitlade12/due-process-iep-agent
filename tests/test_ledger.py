"""Tests for the deterministic delivery ledger."""

from datetime import date, timedelta

import pytest

from due_process.ledger import accounting_residual, compute_ledger, required_sessions_for
from due_process.models import (
    DeliverySetting,
    ExcusedClass,
    FrequencyPeriod,
    LogStatus,
    ServiceCommitment,
    ServiceLog,
    ServiceType,
)
from due_process.scenarios import (
    compliant_speech,
    incomplete_logs_speech,
    worked_example_speech,
)


def _commitment(duration=30, freq=3):
    return ServiceCommitment(
        id="c1",
        service_type=ServiceType.SPEECH_LANGUAGE,
        frequency_count=freq,
        frequency_period=FrequencyPeriod.WEEK,
        duration_minutes=duration,
    )


def test_required_sessions_for():
    assert required_sessions_for(_commitment(freq=3), 36) == 108


def test_worked_example_matches_spec_numbers():
    s = worked_example_speech()
    led = compute_ledger(
        s.commitment, s.logs,
        window_start=s.window_start, window_end=s.window_end,
        instructional_periods=s.instructional_periods,
    )
    assert led.required_sessions == 108
    assert led.required_minutes == 3240
    assert led.delivered_sessions == 72
    assert led.delivered_minutes == 2160
    assert led.excused_sessions == 12
    assert led.excused_minutes == 360
    assert led.unexcused_missed_sessions == 24
    assert led.unexcused_missed_minutes == 720
    assert led.unexcused_shortfall_minutes == 720
    assert led.logs_complete is True
    # 720 / 3240 = 22.22%
    assert round(float(led.shortfall_pct), 4) == 0.2222


def test_worked_example_accounting_balances():
    s = worked_example_speech()
    led = compute_ledger(
        s.commitment, s.logs,
        window_start=s.window_start, window_end=s.window_end,
        instructional_periods=s.instructional_periods,
    )
    # required == delivered + excused + unexcused + pending + unlogged
    assert accounting_residual(led) == 0


def test_compliant_school_has_no_shortfall():
    s = compliant_speech()
    led = compute_ledger(
        s.commitment, s.logs,
        window_start=s.window_start, window_end=s.window_end,
        instructional_periods=s.instructional_periods,
    )
    assert led.delivered_minutes == 3240
    assert led.unexcused_shortfall_minutes == 0
    assert led.logs_complete is True


def test_incomplete_logs_flagged():
    s = incomplete_logs_speech()
    led = compute_ledger(
        s.commitment, s.logs,
        window_start=s.window_start, window_end=s.window_end,
        instructional_periods=s.instructional_periods,
    )
    assert led.unlogged_sessions == 54
    assert led.unlogged_minutes == 54 * 30
    assert led.logs_complete is False


def test_short_session_shortfall():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="l1", commitment_id="c1", date=date(2025, 9, 2),
                   minutes_delivered=10, status=LogStatus.SHORT,
                   excused=ExcusedClass.UNEXCUSED),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=1)
    assert led.delivered_minutes == 10
    assert led.short_sessions == 1
    assert led.short_shortfall_minutes == 20
    assert led.unexcused_shortfall_minutes == 20


def test_excused_missed_not_counted_as_shortfall():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="l1", commitment_id="c1", date=date(2025, 9, 2),
                   minutes_delivered=0, status=LogStatus.MISSED,
                   excused=ExcusedClass.EXCUSED, missed_reason_text="absent"),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=1)
    assert led.excused_minutes == 30
    assert led.unexcused_shortfall_minutes == 0


def test_ambiguous_missed_held_out_of_shortfall():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="l1", commitment_id="c1", date=date(2025, 9, 2),
                   minutes_delivered=0, status=LogStatus.MISSED,
                   excused=ExcusedClass.AMBIGUOUS),
        ServiceLog(id="l2", commitment_id="c1", date=date(2025, 9, 4),
                   minutes_delivered=0, status=LogStatus.MISSED,
                   excused=ExcusedClass.UNCLASSIFIED),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=2)
    assert led.ambiguous_sessions == 2
    assert led.ambiguous_minutes == 60
    # Not actionable until a human classifies them.
    assert led.unexcused_shortfall_minutes == 0


def test_logs_outside_window_ignored():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="in", commitment_id="c1", date=date(2025, 9, 15),
                   minutes_delivered=30, status=LogStatus.DELIVERED),
        ServiceLog(id="out", commitment_id="c1", date=date(2025, 12, 1),
                   minutes_delivered=30, status=LogStatus.DELIVERED),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=4)
    assert led.delivered_sessions == 1
    assert led.delivered_minutes == 30


def test_other_commitment_logs_ignored():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="mine", commitment_id="c1", date=date(2025, 9, 2),
                   minutes_delivered=30, status=LogStatus.DELIVERED),
        ServiceLog(id="other", commitment_id="c2", date=date(2025, 9, 3),
                   minutes_delivered=30, status=LogStatus.DELIVERED),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=4)
    assert led.delivered_sessions == 1


def test_bad_window_raises():
    c = _commitment()
    with pytest.raises(ValueError):
        compute_ledger(c, [], window_start=date(2025, 9, 30),
                       window_end=date(2025, 9, 1), required_sessions=1)


def test_missing_required_sessions_raises():
    c = _commitment()
    with pytest.raises(ValueError):
        compute_ledger(c, [], window_start=date(2025, 9, 1),
                       window_end=date(2025, 9, 30))


def test_makeup_resolves_missed_session():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="miss-1", commitment_id="c1", date=date(2025, 9, 4),
                   minutes_delivered=0, status=LogStatus.MISSED,
                   excused=ExcusedClass.UNEXCUSED),
        ServiceLog(id="mk-1", commitment_id="c1", date=date(2025, 9, 20),
                   minutes_delivered=30, status=LogStatus.DELIVERED,
                   makeup_for="miss-1"),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=1)
    assert led.resolved_by_makeup_minutes == 30
    assert led.unexcused_shortfall_minutes == 0  # cured, no longer owed
    assert led.unlogged_sessions == 0            # the make-up isn't a scheduled slot
    assert accounting_residual(led) == 0


def test_partial_makeup_leaves_remainder_owed():
    c = _commitment(duration=30)
    logs = [
        ServiceLog(id="miss-1", commitment_id="c1", date=date(2025, 9, 4),
                   minutes_delivered=0, status=LogStatus.MISSED,
                   excused=ExcusedClass.UNEXCUSED),
        ServiceLog(id="mk-1", commitment_id="c1", date=date(2025, 9, 20),
                   minutes_delivered=20, status=LogStatus.DELIVERED,
                   makeup_for="miss-1"),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=1)
    assert led.resolved_by_makeup_minutes == 20
    assert led.unexcused_shortfall_minutes == 10  # the uncured remainder
    assert accounting_residual(led) == 0
