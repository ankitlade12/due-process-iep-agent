"""Tests for the Streamlit case desk backend payload."""

import pytest

from due_process.examples.case_desk import (
    _inject_css,
    build_case_payload,
    build_run_payload,
    finalize_case_review,
    prepare_case_review,
)
from due_process.examples.redacted_case import (
    REDACTED_CASE_END,
    REDACTED_CASE_IEP_TEXT,
    REDACTED_CASE_LOG_CSV,
    REDACTED_CASE_PERIODS,
    REDACTED_CASE_PROVIDER_NOTE,
    REDACTED_CASE_START,
    REDACTED_CASE_STUDENT,
)
from due_process.ingest import load_logs_csv
from due_process.instruments.drafter import LetterContext
from due_process.scenarios import compliant_speech
from due_process.scenarios import worked_example_speech


class _CssCapture:
    def __init__(self):
        self.css = ""

    def markdown(self, body, **_kwargs):
        self.css = body


def test_sidebar_form_values_remain_legible_on_light_controls():
    capture = _CssCapture()

    _inject_css(capture)

    assert '[data-testid="stSidebar"] input' in capture.css
    assert "-webkit-text-fill-color: #172026 !important" in capture.css
    assert '[data-testid="stFileUploaderDropzone"] *' in capture.css
    assert '[data-testid="stDownloadButton"] button *' in capture.css



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


def test_packaged_redacted_case_exercises_upload_and_human_review():
    logs = load_logs_csv(
        REDACTED_CASE_LOG_CSV,
        "uploaded-service",
        source_uri="uploaded://service-log.csv",
    )
    review = prepare_case_review(
        iep_text=REDACTED_CASE_IEP_TEXT,
        logs=logs,
        window_start=REDACTED_CASE_START,
        window_end=REDACTED_CASE_END,
        instructional_periods=REDACTED_CASE_PERIODS,
        context=LetterContext(student_name=REDACTED_CASE_STUDENT),
        use_qwen=False,
    )

    ambiguities = review.ambiguity_rows()
    assert len(logs) == 24
    assert len(ambiguities) == 1
    assert ambiguities[0]["reason"] == "See provider note"
    assert "assessment coverage" in REDACTED_CASE_PROVIDER_NOTE
    assert "no substitute provider" in REDACTED_CASE_PROVIDER_NOTE

    commitment = review.commitment
    payload = finalize_case_review(
        review,
        service_type=commitment.service_type.value,
        frequency_count=commitment.frequency_count,
        frequency_period=commitment.frequency_period.value,
        duration_minutes=commitment.duration_minutes,
        setting=commitment.setting.value,
        location=(commitment.location.value if commitment.location else ""),
        ambiguity_decisions={ambiguities[0]["id"]: "unexcused"},
    )

    assert payload["ledger"]["required_minutes"] == 720
    assert payload["ledger"]["delivered_minutes"] == 480
    assert payload["ledger"]["unexcused_minutes"] == 150
    assert payload["ledger"]["shortfall_pct"] == "20.8%"
    assert payload["deterministic"]["material"] is True


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


def test_case_desk_requires_all_ambiguities_before_final_analysis():
    scenario = worked_example_speech(classified=False)
    ambiguous = next(log for log in scenario.logs if log.status.value == "missed")
    ambiguous.missed_reason_text = "See provider note"
    review = prepare_case_review(
        iep_text=scenario.iep_text,
        logs=scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        instructional_periods=scenario.instructional_periods,
        context=LetterContext(student_name="Student A"),
        use_qwen=False,
    )
    commitment = review.commitment

    with pytest.raises(ValueError, match="Resolve every ambiguous"):
        finalize_case_review(
            review,
            service_type=commitment.service_type.value,
            frequency_count=commitment.frequency_count,
            frequency_period=commitment.frequency_period.value,
            duration_minutes=commitment.duration_minutes,
            setting=commitment.setting.value,
        )

    payload = finalize_case_review(
        review,
        service_type=commitment.service_type.value,
        frequency_count=commitment.frequency_count,
        frequency_period=commitment.frequency_period.value,
        duration_minutes=commitment.duration_minutes,
        setting=commitment.setting.value,
        ambiguity_decisions={ambiguous.id: "unexcused"},
    )
    assert payload["ledger"]["unexcused_minutes"] == 720
    checkpoints = {item["kind"]: item for item in payload["checkpoints"]}
    assert checkpoints["confirm_commitments"]["resolved"] is True
    assert checkpoints["review_ambiguous"]["resolved"] is True


def test_case_desk_uses_human_edited_commitment_values():
    scenario = compliant_speech()
    review = prepare_case_review(
        iep_text=(
            "Speech-Language Therapy: 3 x 30 minutes per week, individual."),
        logs=scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        instructional_periods=scenario.instructional_periods,
        context=LetterContext(student_name="Student A"),
        use_qwen=False,
    )
    commitment = review.commitment
    payload = finalize_case_review(
        review,
        service_type=commitment.service_type.value,
        frequency_count=2,
        frequency_period=commitment.frequency_period.value,
        duration_minutes=20,
        setting=commitment.setting.value,
    )
    assert payload["ledger"]["required_sessions"] == 72
    assert payload["ledger"]["required_minutes"] == 1440
