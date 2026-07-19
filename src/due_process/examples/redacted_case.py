"""Packaged, de-identified case assets for the public upload demonstration."""

from __future__ import annotations

from datetime import date
from importlib.resources import files

REDACTED_CASE_STUDENT = "Student R-104"
REDACTED_CASE_SCHOOL = "Cedar Grove Elementary"
REDACTED_CASE_DISTRICT = "Harbor Unified District"
REDACTED_CASE_PERIODS = 12
REDACTED_CASE_START = date(2025, 9, 2)
REDACTED_CASE_END = date(2025, 11, 20)

_DATA = files("due_process.examples").joinpath("data")
REDACTED_CASE_IEP_TEXT = _DATA.joinpath(
    "redacted_iep_service.txt").read_text(encoding="utf-8").strip()
REDACTED_CASE_LOG_CSV = _DATA.joinpath(
    "redacted_service_log.csv").read_text(encoding="utf-8")
REDACTED_CASE_PROVIDER_NOTE = _DATA.joinpath(
    "redacted_provider_note.txt").read_text(encoding="utf-8").strip()
