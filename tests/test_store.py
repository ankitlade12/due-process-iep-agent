"""Tests for persistence and the deadline guard."""

from datetime import date

from due_process.store import CaseStore, agenda, recompute, upcoming_deadlines
from due_process.scenarios import worked_example_speech

TODAY = date(2026, 6, 30)


def _seed():
    s = worked_example_speech()
    store = CaseStore(":memory:")
    store.save_case("case-1", window_start=s.window_start,
                    window_end=s.window_end,
                    instructional_periods=s.instructional_periods,
                    student_name="A. Doe", discovery_date=s.discovery_date)
    store.save_commitment("case-1", s.commitment)
    store.add_logs("case-1", s.logs)
    return store, s


def test_round_trip_commitments_and_logs():
    store, s = _seed()
    assert store.list_cases() == ["case-1"]
    commitments = store.load_commitments("case-1")
    assert len(commitments) == 1
    assert commitments[0].duration_minutes == 30
    assert commitments[0].service_type == s.commitment.service_type
    logs = store.load_logs("case-1")
    assert len(logs) == 108


def test_recompute_reproduces_analysis():
    store, _ = _seed()
    analyses = recompute(store, "case-1", TODAY)
    assert len(analyses) == 1
    assert analyses[0].materiality.is_material is True
    assert analyses[0].ledger.unexcused_shortfall_minutes == 720


def test_agenda_surfaces_owed_and_deadline():
    store, _ = _seed()
    a = agenda(store, "case-1", TODAY, within_days=1000)
    assert a.material_services == 1
    assert a.total_compensatory_minutes == 720
    assert a.approaching_deadlines  # the SoL clock surfaced
    assert a.approaching_deadlines[0][1] > 0  # days remaining


def test_state_complaint_deadline_is_caught_as_approaching():
    store, _ = _seed()
    # The 1-year state-complaint window (~64 days out) IS surfaced by the default
    # 90-day guard — the trap the old 2-year-only logic missed.
    a = agenda(store, "case-1", TODAY)
    assert a.approaching_deadlines
    assert 0 < a.approaching_deadlines[0][1] < 90


def test_deadline_not_flagged_with_tight_window():
    store, _ = _seed()
    a = agenda(store, "case-1", TODAY, within_days=10)
    assert a.approaching_deadlines == []


def test_upcoming_deadlines_sorted():
    store, _ = _seed()
    analyses = recompute(store, "case-1", TODAY)
    pairs = upcoming_deadlines(analyses, within_days=2000)
    assert pairs
    days = [c.days_remaining for _, c in pairs]
    assert days == sorted(days)
