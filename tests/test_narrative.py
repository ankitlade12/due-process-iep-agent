"""Tests for the narrative/summary writer (offline template path)."""

from datetime import date

from due_process.analysis import analyze_commitment
from due_process.llm.narrative import parent_receipt, summarize_pattern
from due_process.scenarios import compliant_speech, worked_example_speech

TODAY = date(2026, 6, 30)


def _analysis():
    s = worked_example_speech()
    return analyze_commitment(
        s.commitment, s.logs, window_start=s.window_start,
        window_end=s.window_end, today=TODAY,
        instructional_periods=s.instructional_periods)


def test_formal_summary_states_facts():
    text = summarize_pattern(_analysis(), style="formal")
    assert "speech language" in text.lower()
    assert "108" in text          # required sessions
    assert "22.2%" in text        # shortfall percentage


def test_summary_does_not_invent_law():
    # The narrative restates facts only; citations are the template's job.
    text = summarize_pattern(_analysis(), style="formal")
    assert "C.F.R." not in text
    assert "§" not in text


def test_plain_summary_is_parent_friendly():
    text = summarize_pattern(_analysis(), style="plain")
    assert "your child" in text.lower()
    assert "720" in text  # unexcused minutes surfaced


def test_language_param_accepted_offline():
    # Offline can't translate; the param must still be accepted without error.
    text = summarize_pattern(_analysis(), style="plain", language="es")
    assert text  # returns the English template, no crash


def test_parent_receipt_is_record_framed():
    text = parent_receipt(_analysis())
    assert "record you can keep" in text.lower()
    # Material case -> surfaces the option to act, gently.
    assert "minutes back" in text.lower() or "state complaint" in text.lower()


def test_parent_receipt_compliant_is_reassuring():
    s = compliant_speech()
    a = analyze_commitment(s.commitment, s.logs, window_start=s.window_start,
                           window_end=s.window_end, today=TODAY,
                           instructional_periods=s.instructional_periods)
    text = parent_receipt(a)
    assert "keeping its promises" in text.lower()
