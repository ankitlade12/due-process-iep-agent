"""Tests for the deterministic materiality rule and violation detection."""

from datetime import date, timedelta
from decimal import Decimal

from due_process.ledger import compute_ledger
from due_process.materiality import (
    MaterialityConfig,
    classify_materiality,
    compensatory_estimate,
    detect_violations,
)
from due_process.models import (
    DeliveryLedger,
    DeliverySetting,
    ExcusedClass,
    FrequencyPeriod,
    LogStatus,
    ServiceCommitment,
    ServiceLog,
    ServiceType,
    ViolationType,
)
from due_process.scenarios import compliant_speech, worked_example_speech


def _ledger(required_minutes, unexcused_missed_minutes):
    """A minimal ledger for boundary tests (logs handled separately)."""
    return DeliveryLedger(
        commitment_id="c1",
        window_start=date(2025, 9, 1),
        window_end=date(2026, 5, 30),
        required_sessions=0,
        required_minutes=required_minutes,
        delivered_sessions=0,
        delivered_minutes=0,
        excused_sessions=0,
        excused_minutes=0,
        unexcused_missed_sessions=0,
        unexcused_missed_minutes=unexcused_missed_minutes,
        short_sessions=0,
        short_shortfall_minutes=0,
        unlogged_sessions=0,
        unlogged_minutes=0,
    )


def test_worked_example_is_material():
    s = worked_example_speech()
    led = compute_ledger(s.commitment, s.logs, window_start=s.window_start,
                         window_end=s.window_end,
                         instructional_periods=s.instructional_periods)
    finding = classify_materiality(led, s.logs)
    assert finding.is_material is True
    assert finding.max_consecutive_unexcused == 1  # spread, so pct rule drives it
    assert "van_duyn" in finding.standard_refs


def test_compliant_is_not_material():
    s = compliant_speech()
    led = compute_ledger(s.commitment, s.logs, window_start=s.window_start,
                         window_end=s.window_end,
                         instructional_periods=s.instructional_periods)
    finding = classify_materiality(led, s.logs)
    assert finding.is_material is False


def test_pct_threshold_boundary_inclusive():
    # Exactly 15% should fire (>=).
    at = classify_materiality(_ledger(1000, 150), [])
    assert at.is_material is True
    # Just under 15% should not.
    below = classify_materiality(_ledger(1000, 149), [])
    assert below.is_material is False


def test_consecutive_rule_fires_when_pct_low():
    # 100 sessions, only 3 missed (3% << 15%) but consecutive -> material.
    c = ServiceCommitment(id="c1", service_type=ServiceType.SPEECH_LANGUAGE,
                          frequency_count=1, frequency_period=FrequencyPeriod.WEEK,
                          duration_minutes=30)
    start = date(2025, 1, 6)
    logs = []
    for i in range(100):
        d = start + timedelta(days=i)
        if i in (10, 11, 12):
            logs.append(ServiceLog(id=f"l{i}", commitment_id="c1", date=d,
                                   minutes_delivered=0, status=LogStatus.MISSED,
                                   excused=ExcusedClass.UNEXCUSED))
        else:
            logs.append(ServiceLog(id=f"l{i}", commitment_id="c1", date=d,
                                   minutes_delivered=30,
                                   status=LogStatus.DELIVERED))
    led = compute_ledger(c, logs, window_start=start,
                         window_end=start + timedelta(days=99),
                         required_sessions=100)
    finding = classify_materiality(led, logs)
    assert float(led.shortfall_pct) < 0.15
    assert finding.max_consecutive_unexcused == 3
    assert finding.is_material is True


def test_config_is_tunable():
    led = _ledger(1000, 100)  # 10%
    strict = classify_materiality(led, [], MaterialityConfig(
        shortfall_pct_threshold=Decimal("0.05")))
    lax = classify_materiality(led, [], MaterialityConfig(
        shortfall_pct_threshold=Decimal("0.25")))
    assert strict.is_material is True
    assert lax.is_material is False


def test_compensatory_estimate_equals_unexcused_shortfall():
    led = _ledger(3240, 720)
    comp = compensatory_estimate(led)
    assert comp.estimated_minutes == 720
    assert comp.is_equitable_estimate is True
    assert "reid_v_dc" in comp.standard_refs


def test_detect_missed_sessions_violation():
    s = worked_example_speech()
    led = compute_ledger(s.commitment, s.logs, window_start=s.window_start,
                         window_end=s.window_end,
                         instructional_periods=s.instructional_periods)
    finding = classify_materiality(led, s.logs)
    violations = detect_violations(s.commitment, led, s.logs, finding)
    missed = [v for v in violations if v.type == ViolationType.MISSED_SESSIONS]
    assert len(missed) == 1
    v = missed[0]
    assert v.shortfall_minutes == 720
    # 24 log refs + 1 IEP ref.
    assert len([r for r in v.evidence_refs
                if r.kind.value == "service_log"]) == 24
    assert "van_duyn" in v.legal_refs


def test_group_dilution_detected():
    c = ServiceCommitment(id="c1", service_type=ServiceType.SPEECH_LANGUAGE,
                          frequency_count=1, frequency_period=FrequencyPeriod.WEEK,
                          duration_minutes=30, setting=DeliverySetting.INDIVIDUAL)
    logs = [
        ServiceLog(id="l1", commitment_id="c1", date=date(2025, 9, 2),
                   minutes_delivered=30, status=LogStatus.DELIVERED,
                   setting_actual=DeliverySetting.GROUP, group_size_actual=4),
    ]
    led = compute_ledger(c, logs, window_start=date(2025, 9, 1),
                         window_end=date(2025, 9, 30), required_sessions=1)
    finding = classify_materiality(led, logs)
    violations = detect_violations(c, led, logs, finding)
    assert any(v.type == ViolationType.GROUP_DILUTION for v in violations)
