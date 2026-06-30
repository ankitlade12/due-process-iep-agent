"""Tests for the systemic evidence engine and district-level drafting."""

from datetime import date

from due_process import corpus
from due_process.analysis import analyze_commitment
from due_process.instruments.drafter import LetterContext, draft_systemic_complaint
from due_process.scenarios import district_caseload
from due_process.systemic import (
    aggregate_systemic,
    StudentCase,
    suppressed_groups,
)

TODAY = date(2026, 6, 30)


def _district_cases():
    district, students, ws, we, periods = district_caseload()
    cases = []
    for sid, commitment, logs in students:
        a = analyze_commitment(commitment, logs, window_start=ws, window_end=we,
                               today=TODAY, instructional_periods=periods)
        cases.append(StudentCase(student_id=sid, district=district, analyses=[a]))
    return district, cases


def test_caseload_has_expected_material_mix():
    _, cases = _district_cases()
    assert len(cases) == 12
    material = sum(1 for c in cases if c.analyses[0].materiality.is_material)
    assert material == 7  # 7 material, 5 not — a realistic district mix


def test_aggregate_produces_one_systemic_finding():
    district, cases = _district_cases()
    findings = aggregate_systemic(cases)
    assert len(findings) == 1
    f = findings[0]
    assert f.district == district
    assert f.n_students_with_service == 12
    assert f.n_students_material == 7
    assert f.meets_k_anonymity is True
    assert f.total_unexcused_minutes > 0


def test_k_anonymity_suppresses_small_cohorts():
    _, cases = _district_cases()
    # Require 20 students; only 12 exist -> nothing may be reported.
    findings = aggregate_systemic(cases, k_threshold=20)
    assert findings == []
    suppressed = suppressed_groups(cases, k_threshold=20)
    assert suppressed and suppressed[0][2] == 12  # 12 students, withheld


def test_low_material_share_is_not_systemic():
    _, cases = _district_cases()
    # Demand 90% of students be material; only ~58% are.
    from decimal import Decimal
    findings = aggregate_systemic(cases, material_share_threshold=Decimal("0.9"))
    assert findings == []


def test_systemic_complaint_is_deidentified_and_grounded():
    district, cases = _district_cases()
    findings = aggregate_systemic(cases)
    inst = draft_systemic_complaint(findings, LetterContext(
        district_name=district, letter_date=TODAY))
    text = inst.draft_text
    assert "Systemic" in text
    assert "300.151" in text
    # No individual student pseudonym leaks into the de-identified complaint.
    assert "S-001" not in text and "S-0" not in text
    corpus.validate_refs(inst.citations)
