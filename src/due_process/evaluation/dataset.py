"""Constructed scenarios for deterministic policy-regression verification.

Each case is constructed with an explicit expected review-signal label (yes/no)
and an expected shortfall-minutes figure generated from the same declared facts.
The cases intentionally encode the product policy and therefore test
implementation consistency, not model accuracy or independent legal validity.
One synthetic scenario is inspired by facts discussed in a published opinion;
it is not a reconstruction of that record or an independently labeled example.
Unexcused sessions are spread (never adjacent) unless a case is specifically
testing the consecutive-sessions rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List

from ..models import (
    DeliverySetting,
    ExcusedClass,
    FrequencyPeriod,
    LogStatus,
    ServiceCommitment,
    ServiceLog,
    ServiceType,
    SourceKind,
    SourceRef,
)

_OFFSETS = (0, 2, 4)
_START = date(2025, 9, 2)


@dataclass
class EvalCase:
    """One labeled scenario for the eval.

    ``provenance`` distinguishes a source-informed synthetic case from the other
    constructed policy cases. Every case in this module remains synthetic.
    """

    name: str
    commitment: ServiceCommitment
    logs: List[ServiceLog]
    window_start: date
    window_end: date
    periods: int
    label_material: bool
    label_comp_minutes: int
    notes: str = ""
    provenance: str = "synthetic_policy_case"


def _session_date(index: int, freq: int) -> date:
    week, slot = divmod(index, freq if freq <= len(_OFFSETS) else len(_OFFSETS))
    offset = _OFFSETS[slot % len(_OFFSETS)] + (slot // len(_OFFSETS))
    return _START + timedelta(days=week * 7 + offset)


def _spread_indices(required: int, count: int, consecutive: bool) -> List[int]:
    if count <= 0:
        return []
    if consecutive:
        return list(range(count))
    step = max(2, required // count)
    idx: List[int] = []
    i = 0
    while len(idx) < count and i < required:
        idx.append(i)
        i += step
    j = 0
    while len(idx) < count:  # top up if step overshot
        if j not in idx:
            idx.append(j)
        j += 1
    return sorted(idx)


def _build_case(
    name: str,
    *,
    label_material: bool,
    delivered: int,
    excused: int,
    unexcused: int,
    short: int = 0,
    short_each: int = 0,
    consecutive: bool = False,
    freq: int = 3,
    dur: int = 30,
    periods: int = 36,
    service: ServiceType = ServiceType.SPEECH_LANGUAGE,
    notes: str = "",
    provenance: str = "synthetic_policy_case",
) -> EvalCase:
    required = freq * periods
    labels: List[str] = [""] * required

    for k in _spread_indices(required, unexcused, consecutive):
        labels[k] = "unexcused"
    remaining = [k for k in range(required) if not labels[k]]
    ptr = 0
    for _ in range(excused):
        labels[remaining[ptr]] = "excused"; ptr += 1
    for _ in range(short):
        labels[remaining[ptr]] = "short"; ptr += 1
    for _ in range(delivered):
        labels[remaining[ptr]] = "delivered"; ptr += 1
    # Any remaining slots stay unlogged (no log row).

    commitment = ServiceCommitment(
        id=f"svc-{name}",
        service_type=service,
        frequency_count=freq,
        frequency_period=FrequencyPeriod.WEEK,
        duration_minutes=dur,
        setting=DeliverySetting.INDIVIDUAL,
        effective_start=_START,
        source_ref=SourceRef(kind=SourceKind.IEP, locator="p.7 §Services",
                             description=f"{service.value} services line",
                             record_id=f"svc-{name}"),
    )

    logs: List[ServiceLog] = []
    for idx, kind in enumerate(labels):
        if not kind:
            continue
        d = _session_date(idx, freq)
        common = dict(id=f"{name}-{idx:03d}", commitment_id=commitment.id, date=d,
                      source_ref=SourceRef(kind=SourceKind.SERVICE_LOG,
                                           locator=d.isoformat(),
                                           record_id=f"{name}-{idx:03d}"))
        if kind == "delivered":
            logs.append(ServiceLog(minutes_delivered=dur,
                                   status=LogStatus.DELIVERED, **common))
        elif kind == "excused":
            logs.append(ServiceLog(minutes_delivered=0, status=LogStatus.MISSED,
                                   excused=ExcusedClass.EXCUSED,
                                   missed_reason_text="Student absent", **common))
        elif kind == "unexcused":
            logs.append(ServiceLog(minutes_delivered=0, status=LogStatus.MISSED,
                                   excused=ExcusedClass.UNEXCUSED,
                                   missed_reason_text="Provider absent, no substitute",
                                   **common))
        elif kind == "short":
            logs.append(ServiceLog(minutes_delivered=max(0, dur - short_each),
                                   status=LogStatus.SHORT,
                                   excused=ExcusedClass.UNEXCUSED,
                                   missed_reason_text="Cut short, staffing",
                                   **common))

    label_comp = unexcused * dur + short * short_each
    return EvalCase(
        name=name, commitment=commitment, logs=logs,
        window_start=_START, window_end=_session_date(required - 1, freq),
        periods=periods, label_material=label_material,
        label_comp_minutes=label_comp, notes=notes, provenance=provenance,
    )


def build_dataset() -> List[EvalCase]:
    """The labeled eval set. Balanced across material / not-material."""
    return [
        _build_case("compliant", label_material=False,
                    delivered=108, excused=0, unexcused=0,
                    notes="Full delivery — must not false-positive."),
        _build_case("worked_example", label_material=True,
                    delivered=72, excused=12, unexcused=24,
                    notes="The product-spec case: 22% unexcused shortfall."),
        _build_case("minor_below_threshold", label_material=False,
                    delivered=100, excused=3, unexcused=5,
                    notes="4.6% unexcused — below the threshold."),
        _build_case("severe", label_material=True,
                    delivered=60, excused=0, unexcused=48,
                    notes="44% unexcused — clear material failure."),
        _build_case("consecutive_run", label_material=True,
                    delivered=103, excused=0, unexcused=5, consecutive=True,
                    notes="Low % but 5 missed in a row — consecutive rule."),
        _build_case("mostly_excused", label_material=False,
                    delivered=80, excused=28, unexcused=0,
                    notes="Many absences, all the child's — not the school's."),
        _build_case("short_sessions_material", label_material=True,
                    delivered=68, excused=0, unexcused=0, short=40, short_each=15,
                    notes="40 sessions cut by half = 18.5% shortfall."),
        _build_case("borderline_below", label_material=False,
                    delivered=90, excused=3, unexcused=15,
                    notes="13.9% — just below the line."),
        _build_case("borderline_above", label_material=True,
                    delivered=88, excused=3, unexcused=17,
                    notes="15.7% — just above the line."),
        _build_case("ot_severe", label_material=True,
                    delivered=40, excused=5, unexcused=27, freq=2,
                    service=ServiceType.OCCUPATIONAL_THERAPY,
                    notes="OT, 2x/week, 37.5% unexcused."),
        _build_case("source_informed_math_shortfall", label_material=True,
                    delivered=54, excused=0, unexcused=54,
                    service=ServiceType.SPECIALIZED_INSTRUCTION,
                    notes="Synthetic 50% math-instruction shortfall inspired "
                          "by the initial shortfall discussed in Van Duyn; not "
                          "a reconstruction of the case record.",
                    provenance="synthetic_source_informed: Van Duyn v. Baker "
                               "Sch. Dist. 5J, 502 F.3d 811 (9th Cir. 2007)"),
    ]
