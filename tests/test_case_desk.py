"""Tests for the Streamlit case desk backend payload."""

from due_process.examples.case_desk import build_run_payload


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
