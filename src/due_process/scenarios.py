"""Synthetic scenarios with known ground truth.

These generators produce IEP-commitment + service-log pairs with labeled
expected outcomes. They serve three callers:

  * the worked-example demo (:mod:`due_process.examples.worked_example`),
  * the deterministic-core unit tests, and
  * the planned precision/recall evaluation, which needs exactly this — synthetic
    pairs with ground-truth labels — to report metrics the incumbents do not.

The flagship scenario reproduces the spec's worked example: 108 required speech
sessions, 72 delivered, 12 excused absences, 24 unexcused → a 720-minute (22%)
unexcused shortfall that crosses the materiality threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List

from .models import (
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

_SESSION_DAY_OFFSETS = (0, 2, 4)  # spread 3 sessions across a week (Mon/Wed/Fri)


@dataclass
class ScenarioData:
    """A synthetic scenario plus its ground-truth labels."""

    name: str
    commitment: ServiceCommitment
    logs: List[ServiceLog]
    window_start: date
    window_end: date
    instructional_periods: int
    discovery_date: date
    expected: Dict = field(default_factory=dict)
    iep_text: str = ""  # the IEP services-page text, for the extraction step


# The services-page text for the flagship scenario — feeds the extraction step.
WORKED_EXAMPLE_IEP_TEXT = (
    "Special Education and Related Services\n"
    "Speech-Language Therapy: 3 x 30 minutes per week, individual, pull-out.\n"
)


def _session_date(start: date, index: int) -> date:
    week, slot = divmod(index, len(_SESSION_DAY_OFFSETS))
    return start + timedelta(days=week * 7 + _SESSION_DAY_OFFSETS[slot])


def _speech_commitment(start: date) -> ServiceCommitment:
    return ServiceCommitment(
        id="svc-speech-1",
        service_type=ServiceType.SPEECH_LANGUAGE,
        frequency_count=3,
        frequency_period=FrequencyPeriod.WEEK,
        duration_minutes=30,
        setting=DeliverySetting.INDIVIDUAL,
        location=ServiceLocation.PULL_OUT,
        provider_qualification="licensed SLP",
        linked_goal_ids=["goal-comm-1"],
        effective_start=start,
        source_ref=SourceRef(
            kind=SourceKind.IEP,
            locator="p.7 §Services",
            description="Speech/language services line",
            uri="oss://ieps/student-123.pdf#page=7",
            record_id="svc-speech-1",
        ),
    )


def _log(commitment_id: str, index: int, d: date, *, status: LogStatus,
         minutes: int, excused: ExcusedClass, reason: str = "",
         setting: DeliverySetting | None = None) -> ServiceLog:
    return ServiceLog(
        id=f"log-{index:03d}",
        commitment_id=commitment_id,
        date=d,
        minutes_delivered=minutes,
        status=status,
        setting_actual=setting,
        provider="SLP Jane Doe" if status != LogStatus.MISSED else "",
        missed_reason_text=reason,
        excused=excused,
        source_ref=SourceRef(
            kind=SourceKind.SERVICE_LOG,
            locator=f"row {index + 1}",
            description=f"Service-log row {index + 1} ({d.isoformat()})",
            uri="oss://logs/student-123-logs.pdf",
            record_id=f"log-{index:03d}",
        ),
    )


def worked_example_speech(start: date = date(2025, 9, 2),
                          classified: bool = True) -> ScenarioData:
    """The spec's worked example: 108 required, 72 delivered, 12 excused, 24 not.

    The 24 unexcused missed sessions are spread (never 3 in a row) so the
    materiality verdict is driven by the 22% percentage rule, matching the spec's
    emphasis rather than the consecutive-sessions rule.

    With ``classified=False`` the missed logs keep their reason text but are left
    ``UNCLASSIFIED`` — for exercising the agent's classification step.
    """
    commitment = _speech_commitment(start)

    def _excused(true_label: ExcusedClass) -> ExcusedClass:
        return true_label if classified else ExcusedClass.UNCLASSIFIED

    logs: List[ServiceLog] = []
    for i in range(108):
        d = _session_date(start, i)
        mod = i % 9
        if mod in (2, 5):  # 24 of 108 -> unexcused
            logs.append(_log(commitment.id, i, d, status=LogStatus.MISSED,
                             minutes=0, excused=_excused(ExcusedClass.UNEXCUSED),
                             reason="Provider absent, no substitute"))
        elif mod == 8:     # 12 of 108 -> excused
            logs.append(_log(commitment.id, i, d, status=LogStatus.MISSED,
                             minutes=0, excused=_excused(ExcusedClass.EXCUSED),
                             reason="Student absent"))
        else:              # 72 of 108 -> delivered
            logs.append(_log(commitment.id, i, d, status=LogStatus.DELIVERED,
                             minutes=30, excused=ExcusedClass.UNCLASSIFIED,
                             setting=DeliverySetting.INDIVIDUAL))

    window_end = _session_date(start, 107)
    return ScenarioData(
        name="worked_example_speech",
        commitment=commitment,
        logs=logs,
        window_start=start,
        window_end=window_end,
        instructional_periods=36,
        discovery_date=window_end,
        iep_text=WORKED_EXAMPLE_IEP_TEXT,
        expected={
            "required_sessions": 108,
            "required_minutes": 3240,
            "delivered_sessions": 72,
            "delivered_minutes": 2160,
            "excused_sessions": 12,
            "excused_minutes": 360,
            "unexcused_missed_sessions": 24,
            "unexcused_shortfall_minutes": 720,
            "logs_complete": True,
            "material_failure": True,
            "comp_minutes": 720,
        },
    )


def compliant_speech(start: date = date(2025, 9, 2)) -> ScenarioData:
    """A school that delivered everything — the must-not-false-positive case."""
    commitment = _speech_commitment(start)
    logs = [
        _log(commitment.id, i, _session_date(start, i),
             status=LogStatus.DELIVERED, minutes=30,
             excused=ExcusedClass.UNCLASSIFIED, setting=DeliverySetting.INDIVIDUAL)
        for i in range(108)
    ]
    window_end = _session_date(start, 107)
    return ScenarioData(
        name="compliant_speech",
        commitment=commitment,
        logs=logs,
        window_start=start,
        window_end=window_end,
        instructional_periods=36,
        discovery_date=window_end,
        expected={
            "required_minutes": 3240,
            "delivered_minutes": 3240,
            "unexcused_shortfall_minutes": 0,
            "logs_complete": True,
            "material_failure": False,
            "comp_minutes": 0,
        },
    )


def incomplete_logs_speech(start: date = date(2025, 9, 2)) -> ScenarioData:
    """Only half the required sessions were ever logged.

    The correct first move here is a service-log request, not a complaint — you
    cannot prove a shortfall you have not documented.
    """
    commitment = _speech_commitment(start)
    logs = [
        _log(commitment.id, i, _session_date(start, i),
             status=LogStatus.DELIVERED, minutes=30,
             excused=ExcusedClass.UNCLASSIFIED, setting=DeliverySetting.INDIVIDUAL)
        for i in range(54)
    ]
    window_end = _session_date(start, 107)
    return ScenarioData(
        name="incomplete_logs_speech",
        commitment=commitment,
        logs=logs,
        window_start=start,
        window_end=window_end,
        instructional_periods=36,
        discovery_date=window_end,
        expected={
            "required_sessions": 108,
            "unlogged_sessions": 54,
            "logs_complete": False,
        },
    )


def _spread_indices(required: int, count: int) -> List[int]:
    """Pick ``count`` session indices spaced apart (so they are not consecutive)."""
    if count <= 0:
        return []
    step = max(2, required // count)
    idx: List[int] = []
    i = 0
    while len(idx) < count and i < required:
        idx.append(i)
        i += step
    j = 0
    while len(idx) < count:
        if j not in idx:
            idx.append(j)
        j += 1
    return sorted(idx)


# (student_id, delivered, excused, unexcused) over 108 required speech sessions.
_DISTRICT_PATTERNS = [
    ("S-001", 72, 12, 24),   # material — the worked example
    ("S-002", 60, 0, 48),    # material — severe
    ("S-003", 108, 0, 0),    # compliant
    ("S-004", 88, 3, 17),    # material — just over the line
    ("S-005", 100, 3, 5),    # not material — minor, spread
    ("S-006", 70, 0, 38),    # material
    ("S-007", 108, 0, 0),    # compliant
    ("S-008", 80, 4, 24),    # material
    ("S-009", 66, 6, 36),    # material
    ("S-010", 108, 0, 0),    # compliant
    ("S-011", 90, 3, 15),    # not material — borderline below, spread
    ("S-012", 84, 0, 24),    # material
]


def district_caseload(district: str = "Springfield SD",
                      start: date = date(2025, 9, 2)):
    """A district's worth of de-identified students for the systemic demo.

    Twelve students all receiving speech services — a realistic mix of material
    failures and compliant cases. Returns (district, students, window_start,
    window_end, instructional_periods) where each student is
    (student_id, commitment, logs).
    """
    required = 108
    students = []
    for sid, delivered, excused, unexcused in _DISTRICT_PATTERNS:
        cid = f"svc-{sid}"
        commitment = ServiceCommitment(
            id=cid,
            service_type=ServiceType.SPEECH_LANGUAGE,
            frequency_count=3,
            frequency_period=FrequencyPeriod.WEEK,
            duration_minutes=30,
            setting=DeliverySetting.INDIVIDUAL,
            location=ServiceLocation.PULL_OUT,
            effective_start=start,
            source_ref=SourceRef(kind=SourceKind.IEP, locator="p.7 §Services",
                                 description=f"{sid} speech line", record_id=cid),
        )
        labels = [""] * required
        for k in _spread_indices(required, unexcused):
            labels[k] = "unexcused"
        remaining = [k for k in range(required) if not labels[k]]
        ptr = 0
        for _ in range(excused):
            labels[remaining[ptr]] = "excused"; ptr += 1
        for _ in range(delivered):
            labels[remaining[ptr]] = "delivered"; ptr += 1

        logs = []
        for idx, kind in enumerate(labels):
            if not kind:
                continue
            d = _session_date(start, idx)
            if kind == "delivered":
                logs.append(_log(cid, idx, d, status=LogStatus.DELIVERED,
                                 minutes=30, excused=ExcusedClass.UNCLASSIFIED,
                                 setting=DeliverySetting.INDIVIDUAL))
            elif kind == "excused":
                logs.append(_log(cid, idx, d, status=LogStatus.MISSED, minutes=0,
                                 excused=ExcusedClass.EXCUSED,
                                 reason="Student absent"))
            else:  # unexcused
                logs.append(_log(cid, idx, d, status=LogStatus.MISSED, minutes=0,
                                 excused=ExcusedClass.UNEXCUSED,
                                 reason="Provider absent, no substitute"))
        students.append((sid, commitment, logs))

    return district, students, start, _session_date(start, required - 1), 36


ALL_SCENARIOS = [
    worked_example_speech,
    compliant_speech,
    incomplete_logs_speech,
]
