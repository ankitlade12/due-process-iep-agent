"""Tests for the Streamlit case desk backend payload."""

from due_process.examples.case_desk import build_case_payload, build_run_payload
from due_process.instruments.drafter import LetterContext
from due_process.scenarios import compliant_speech



def test_case_desk_payload_contains_core_demo_signals():
    payload = build_run_payload(use_qwen=False)

    assert payload["mode"] == "offline-fallback"
    assert payload["status"] == "needs_human_approval"
    assert len(payload["agent_steps"]) == 6
    assert payload["ledger"]["unexcused_minutes"] == 720
    assert payload["deterministic"]["material"] is True
    assert payload["claims"][0]["logs"]
    assert payload["systemic"]["students_material"] == 7


def test_case_desk_payload_keeps_draft_and_audit():
    payload = build_run_payload(use_qwen=False)

    assert "State Complaint" in payload["draft"]["text"]
    assert payload["audit"]
    assert "Parsed 1 commitment" in payload["audit"][0]


def test_case_desk_handles_uploaded_compliant_case_without_false_claim():
    scenario = compliant_speech()
    payload = build_case_payload(
        iep_text=(
            "Speech-Language Therapy: 3 x 30 minutes per week, "
            "individual, pull-out."),
        logs=scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        instructional_periods=scenario.instructional_periods,
        context=LetterContext(student_name="Student A"),
        use_qwen=False,
    )

    assert payload["deterministic"]["material"] is False
    assert payload["ledger"]["unexcused_minutes"] == 0
    assert payload["systemic"] is None
    assert payload["claims"][0]["title"] == "No actionable violation generated"
