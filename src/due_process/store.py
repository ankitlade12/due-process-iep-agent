"""Persistence + the deadline guard — make it a year-round tool, not a one-shot.

Enforcement is a months-long process: the IEP is signed in the fall, logs trickle
in, and the two-year filing clock runs the whole time. A real tool has to
*remember* across sessions and *warn* before the deadline passes — parents lose
valid claims simply by losing track.

This is a small, dependency-free SQLite store (stdlib ``sqlite3``). It persists
the inputs (the IEP commitments and the service logs); everything derived — the
ledger, violations, deadlines — is recomputed on load, so there is one source of
truth and the deterministic core stays authoritative.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from .analysis import CommitmentAnalysis, analyze_commitment
from .deadlines import is_urgent
from .models import (
    DeadlineClock,
    DeliverySetting,
    ExcusedClass,
    FrequencyPeriod,
    LogStatus,
    ServiceCommitment,
    ServiceLocation,
    ServiceLog,
    ServiceType,
    SourceKind,
    SourceRef,
)


# --------------------------------------------------------------------------- #
# (De)serialization — explicit, so dates and enums round-trip correctly
# --------------------------------------------------------------------------- #
def _date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def _ref_to_dict(r: Optional[SourceRef]) -> Optional[dict]:
    if r is None:
        return None
    return {"kind": r.kind.value, "locator": r.locator,
            "description": r.description, "uri": r.uri, "record_id": r.record_id}


def _ref_from_dict(d: Optional[dict]) -> Optional[SourceRef]:
    if not d:
        return None
    return SourceRef(kind=SourceKind(d["kind"]), locator=d.get("locator", ""),
                     description=d.get("description", ""), uri=d.get("uri", ""),
                     record_id=d.get("record_id", ""))


def _commitment_to_dict(c: ServiceCommitment) -> dict:
    return {
        "id": c.id, "service_type": c.service_type.value,
        "frequency_count": c.frequency_count,
        "frequency_period": c.frequency_period.value,
        "duration_minutes": c.duration_minutes, "setting": c.setting.value,
        "location": c.location.value if c.location else None,
        "group_size_max": c.group_size_max,
        "provider_qualification": c.provider_qualification,
        "linked_goal_ids": c.linked_goal_ids,
        "effective_start": c.effective_start.isoformat() if c.effective_start else None,
        "effective_end": c.effective_end.isoformat() if c.effective_end else None,
        "source_ref": _ref_to_dict(c.source_ref),
    }


def _commitment_from_dict(d: dict) -> ServiceCommitment:
    return ServiceCommitment(
        id=d["id"], service_type=ServiceType(d["service_type"]),
        frequency_count=d["frequency_count"],
        frequency_period=FrequencyPeriod(d["frequency_period"]),
        duration_minutes=d["duration_minutes"],
        setting=DeliverySetting(d.get("setting", "individual")),
        location=ServiceLocation(d["location"]) if d.get("location") else None,
        group_size_max=d.get("group_size_max"),
        provider_qualification=d.get("provider_qualification", ""),
        linked_goal_ids=d.get("linked_goal_ids", []),
        effective_start=_date(d.get("effective_start")),
        effective_end=_date(d.get("effective_end")),
        source_ref=_ref_from_dict(d.get("source_ref")),
    )


def _log_to_dict(l: ServiceLog) -> dict:
    return {
        "id": l.id, "commitment_id": l.commitment_id, "date": l.date.isoformat(),
        "minutes_delivered": l.minutes_delivered, "status": l.status.value,
        "setting_actual": l.setting_actual.value if l.setting_actual else None,
        "group_size_actual": l.group_size_actual, "provider": l.provider,
        "missed_reason_text": l.missed_reason_text, "excused": l.excused.value,
        "source_ref": _ref_to_dict(l.source_ref), "makeup_for": l.makeup_for,
    }


def _log_from_dict(d: dict) -> ServiceLog:
    return ServiceLog(
        id=d["id"], commitment_id=d["commitment_id"], date=_date(d["date"]),
        minutes_delivered=d.get("minutes_delivered", 0),
        status=LogStatus(d.get("status", "delivered")),
        setting_actual=(DeliverySetting(d["setting_actual"])
                        if d.get("setting_actual") else None),
        group_size_actual=d.get("group_size_actual"),
        provider=d.get("provider", ""),
        missed_reason_text=d.get("missed_reason_text", ""),
        excused=ExcusedClass(d.get("excused", "unclassified")),
        source_ref=_ref_from_dict(d.get("source_ref")),
        makeup_for=d.get("makeup_for"),
    )


# --------------------------------------------------------------------------- #
# The store
# --------------------------------------------------------------------------- #
class CaseStore:
    """A SQLite-backed store for student cases (commitments + logs + metadata)."""

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY, student_name TEXT, state TEXT,
                window_start TEXT, window_end TEXT,
                instructional_periods INTEGER, discovery_date TEXT
            );
            CREATE TABLE IF NOT EXISTS commitments (
                case_id TEXT, commitment_id TEXT, data TEXT,
                PRIMARY KEY (case_id, commitment_id)
            );
            CREATE TABLE IF NOT EXISTS logs (
                case_id TEXT, log_id TEXT, data TEXT,
                PRIMARY KEY (case_id, log_id)
            );
            """
        )
        self.conn.commit()

    def save_case(self, case_id: str, *, window_start: date, window_end: date,
                  instructional_periods: int, student_name: str = "",
                  state: str = "", discovery_date: Optional[date] = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?)",
            (case_id, student_name, state, window_start.isoformat(),
             window_end.isoformat(), instructional_periods,
             discovery_date.isoformat() if discovery_date else None),
        )
        self.conn.commit()

    def get_case(self, case_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return dict(row) if row else None

    def list_cases(self) -> List[str]:
        return [r["case_id"] for r in
                self.conn.execute("SELECT case_id FROM cases").fetchall()]

    def save_commitment(self, case_id: str, commitment: ServiceCommitment) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO commitments VALUES (?,?,?)",
            (case_id, commitment.id, json.dumps(_commitment_to_dict(commitment))))
        self.conn.commit()

    def add_logs(self, case_id: str, logs: List[ServiceLog]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO logs VALUES (?,?,?)",
            [(case_id, l.id, json.dumps(_log_to_dict(l))) for l in logs])
        self.conn.commit()

    def load_commitments(self, case_id: str) -> List[ServiceCommitment]:
        rows = self.conn.execute(
            "SELECT data FROM commitments WHERE case_id=?", (case_id,)).fetchall()
        return [_commitment_from_dict(json.loads(r["data"])) for r in rows]

    def load_logs(self, case_id: str) -> List[ServiceLog]:
        rows = self.conn.execute(
            "SELECT data FROM logs WHERE case_id=?", (case_id,)).fetchall()
        return [_log_from_dict(json.loads(r["data"])) for r in rows]

    def close(self) -> None:
        self.conn.close()


# --------------------------------------------------------------------------- #
# Recompute + the deadline guard
# --------------------------------------------------------------------------- #
def recompute(store: CaseStore, case_id: str, today: date
              ) -> List[CommitmentAnalysis]:
    """Load a case and re-run the deterministic analysis for each commitment."""
    meta = store.get_case(case_id)
    if meta is None:
        raise KeyError(f"No such case: {case_id}")
    logs = store.load_logs(case_id)
    analyses = []
    for commitment in store.load_commitments(case_id):
        analyses.append(analyze_commitment(
            commitment, logs,
            window_start=_date(meta["window_start"]),
            window_end=_date(meta["window_end"]),
            today=today,
            instructional_periods=meta["instructional_periods"],
            discovery_date=_date(meta["discovery_date"]),
            state=meta["state"] or "",
        ))
    return analyses


def upcoming_deadlines(
    analyses: List[CommitmentAnalysis],
    within_days: int = 90,
) -> List[Tuple[CommitmentAnalysis, DeadlineClock]]:
    """Violations whose filing deadline is approaching (or past), soonest first."""
    pairs: List[Tuple[CommitmentAnalysis, DeadlineClock]] = []
    for a in analyses:
        for clock in a.deadlines:
            if is_urgent(clock, within_days):
                pairs.append((a, clock))
    pairs.sort(key=lambda p: p[1].days_remaining)
    return pairs


@dataclass
class Agenda:
    """What needs attention on a case right now."""

    case_id: str
    material_services: int = 0
    needs_logs: bool = False
    total_compensatory_minutes: int = 0
    approaching_deadlines: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def has_urgent_deadline(self) -> bool:
        return any(days < 30 for _, days in self.approaching_deadlines)


def agenda(store: CaseStore, case_id: str, today: date,
           within_days: int = 90) -> Agenda:
    """A glance at a case: what's material, what's owed, what's due soon."""
    analyses = recompute(store, case_id, today)
    result = Agenda(case_id=case_id)
    for a in analyses:
        if a.materiality.is_material:
            result.material_services += 1
        if a.needs_logs_first:
            result.needs_logs = True
        if a.compensatory:
            result.total_compensatory_minutes += a.compensatory.estimated_minutes
    for a, clock in upcoming_deadlines(analyses, within_days):
        result.approaching_deadlines.append(
            (a.commitment.service_type.value, clock.days_remaining))
    return result
