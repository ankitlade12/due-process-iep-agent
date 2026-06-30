"""End-to-end tests of the deterministic analysis pipeline."""

from datetime import date

from due_process.analysis import analyze_commitment
from due_process.grounding import assert_grounded
from due_process.models import ViolationType
from due_process.scenarios import (
    compliant_speech,
    incomplete_logs_speech,
    worked_example_speech,
)

TODAY = date(2026, 6, 30)


def _run(scenario):
    return analyze_commitment(
        scenario.commitment,
        scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        today=TODAY,
        instructional_periods=scenario.instructional_periods,
        discovery_date=scenario.discovery_date,
    )


def test_worked_example_pipeline():
    s = worked_example_speech()
    a = _run(s)
    assert a.has_actionable_violation is True
    assert a.compensatory.estimated_minutes == s.expected["comp_minutes"]

    missed = [v for v in a.violations if v.type == ViolationType.MISSED_SESSIONS]
    assert len(missed) == 1
    assert missed[0].shortfall_minutes == 720

    # Every violation must be fully grounded.
    for v in a.violations:
        assert_grounded(v)

    # Primary deadline is the 1-year state-complaint window (34 CFR 300.153(c)).
    assert a.deadlines[0].remedy == "state_complaint"
    assert a.deadlines[0].limitations_years == 1
    # The 2-year due-process alternative is also computed and further out.
    assert a.due_process_deadlines[0].remedy == "due_process"
    assert a.due_process_deadlines[0].limitations_years == 2
    assert (a.due_process_deadlines[0].sol_expiry_date
            > a.deadlines[0].sol_expiry_date)


def test_compliant_pipeline_flags_nothing():
    a = _run(compliant_speech())
    assert a.has_actionable_violation is False
    assert a.violations == []
    assert a.compensatory.estimated_minutes == 0


def test_incomplete_logs_requests_logs_first():
    a = _run(incomplete_logs_speech())
    assert a.needs_logs_first is True


def test_all_pipeline_bundles_are_complete():
    a = _run(worked_example_speech())
    assert len(a.bundles) == len(a.violations)
    for bundle in a.bundles:
        assert bundle.is_complete()
