"""Tests for FERPA PII redaction."""

from due_process.privacy import Redactor, redact_for_cloud


def _redactor():
    return Redactor.for_case(
        student_name="Maria Gonzalez",
        parent_name="Ana Gonzalez",
        student_id="STU-12345",
    )


def test_redacts_known_identifiers():
    r = _redactor()
    text = "Maria Gonzalez missed her speech session. Student ID STU-12345."
    redacted, _ = r.redact(text)
    assert "Maria" not in redacted
    assert "Gonzalez" not in redacted
    assert "STU-12345" not in redacted
    assert "[STUDENT]" in redacted


def test_redacts_generic_pii():
    r = _redactor()
    text = "Contact ana@example.com or 555-123-4567. DOB: 01/02/2015."
    redacted, _ = r.redact(text)
    assert "ana@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "01/02/2015" not in redacted


def test_preserves_session_dates():
    # Service dates are evidence — they must NOT be redacted.
    r = _redactor()
    redacted, _ = r.redact("Session on 2025-09-04 was missed (provider absent).")
    assert "2025-09-04" in redacted


def test_leaks_empty_after_redaction():
    r = _redactor()
    redacted, _ = r.redact("Maria Gonzalez, STU-12345")
    assert r.leaks(redacted) == []


def test_restore_round_trip():
    r = _redactor()
    text = "Maria Gonzalez needs more support."
    redacted, restore = r.redact(text)
    assert r.restore(redacted, restore) == text


def test_redact_for_cloud_noop_without_redactor():
    assert redact_for_cloud("Maria Gonzalez", None) == "Maria Gonzalez"


def test_redact_for_cloud_blocks_leak():
    r = _redactor()
    out = redact_for_cloud("Maria Gonzalez missed speech", r)
    assert "Maria" not in out and "[STUDENT]" in out
