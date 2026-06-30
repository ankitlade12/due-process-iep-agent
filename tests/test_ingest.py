"""Tests for ingesting real service-log files."""

from datetime import date

import pytest

from due_process.ingest import load_logs_csv
from due_process.models import LogStatus

_CSV = """Session Date,Minutes,Status,Reason,Provider
2025-09-04,0,Missed,Provider absent no sub,
2025-09-06,30,Delivered,,SLP Jane
2025-09-08,15,,,SLP Jane
2025-09-10,30,Present,,SLP Jane
"""


def test_csv_import_basic():
    logs = load_logs_csv(_CSV, "c1", scheduled_minutes=30)
    assert len(logs) == 4
    assert logs[0].date == date(2025, 9, 4)
    assert logs[0].status == LogStatus.MISSED
    assert logs[0].missed_reason_text == "Provider absent no sub"
    assert logs[1].status == LogStatus.DELIVERED
    assert logs[1].minutes_delivered == 30
    assert logs[1].provider == "SLP Jane"


def test_short_session_inferred_from_minutes():
    logs = load_logs_csv(_CSV, "c1", scheduled_minutes=30)
    # Row with 15 minutes and no status, vs 30 scheduled -> SHORT.
    assert logs[2].status == LogStatus.SHORT
    assert logs[2].minutes_delivered == 15


def test_present_word_is_delivered():
    logs = load_logs_csv(_CSV, "c1", scheduled_minutes=30)
    assert logs[3].status == LogStatus.DELIVERED


def test_fuzzy_headers_and_us_dates():
    csv_text = "Day,Mins,Attendance,Therapist\n09/04/2025,30,delivered,Ms. Lee\n"
    logs = load_logs_csv(csv_text, "c2")
    assert len(logs) == 1
    assert logs[0].date == date(2025, 9, 4)
    assert logs[0].minutes_delivered == 30
    assert logs[0].provider == "Ms. Lee"


def test_commitment_id_propagated():
    logs = load_logs_csv(_CSV, "svc-abc", scheduled_minutes=30)
    assert all(l.commitment_id == "svc-abc" for l in logs)


def test_missing_date_column_raises():
    with pytest.raises(ValueError):
        load_logs_csv("Minutes,Status\n30,Delivered\n", "c1")
