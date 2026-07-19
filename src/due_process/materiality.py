"""Deterministic review-screening rule, finding detection, and comp-time estimate.

The Ninth Circuit's *Van Duyn* opinion discusses material failure to implement an
IEP, but it does not create this product's percentage or consecutive-session
thresholds. Those values are a **transparent, configurable screening policy**—not
a legal test or model judgment. Crossing a threshold means "escalate for human
review," not "a violation occurred."

Everything in this module is deterministic and unit-tested. The LLM never
decides materiality; at most it narrates the already-decided result into the
``llm_rationale`` field downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .models import (
    CompensatoryEstimate,
    DeliveryLedger,
    DeliverySetting,
    ExcusedClass,
    LogStatus,
    MaterialityFinding,
    ServiceCommitment,
    ServiceLog,
    SourceKind,
    SourceRef,
    Violation,
    ViolationType,
)


@dataclass(frozen=True)
class MaterialityConfig:
    """The materiality rule's tunable parameters.

    These numbers are policy, stated openly, not hidden in a model. A deployment
    documents whatever threshold it uses and cites the material-failure standard
    as the rationale.
    """

    # Product review thresholds, not statutory bright lines. Crossing one means
    # "escalate for review," not "a court has found a violation."
    shortfall_pct_threshold: Decimal = Decimal("0.15")
    consecutive_missed_threshold: int = 3
    # The standards a materiality finding is grounded to (corpus ids).
    standard_refs: tuple = ("cfr_300_323", "van_duyn")


DEFAULT_CONFIG = MaterialityConfig()


def _max_consecutive_unexcused_missed(logs: List[ServiceLog]) -> int:
    """Longest run of consecutive unexcused *missed* sessions, by date."""
    run = 0
    best = 0
    for log in sorted(logs, key=lambda x: x.date):
        if log.status == LogStatus.MISSED and log.excused == ExcusedClass.UNEXCUSED:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def classify_materiality(
    ledger: DeliveryLedger,
    logs: List[ServiceLog],
    config: MaterialityConfig = DEFAULT_CONFIG,
) -> MaterialityFinding:
    """Apply the deterministic materiality rule to a computed ledger."""
    pct = ledger.shortfall_pct
    consecutive = _max_consecutive_unexcused_missed([
        log for log in logs
        if log.commitment_id == ledger.commitment_id
        and ledger.window_start <= log.date <= ledger.window_end
    ])

    reasons: List[str] = []
    pct_fired = pct >= config.shortfall_pct_threshold
    run_fired = consecutive >= config.consecutive_missed_threshold

    if pct_fired:
        reasons.append(
            f"Unexcused shortfall is {pct:.1%} of required minutes "
            f"({ledger.unexcused_shortfall_minutes} of {ledger.required_minutes}), "
            f"at or above the {config.shortfall_pct_threshold:.0%} review threshold."
        )
    if run_fired:
        reasons.append(
            f"{consecutive} consecutive unexcused missed sessions, at or above "
            f"the review threshold of {config.consecutive_missed_threshold}."
        )
    if not reasons:
        reasons.append(
            f"Unexcused shortfall is {pct:.1%} of required minutes, below the "
            f"{config.shortfall_pct_threshold:.0%} review threshold, and the longest run "
            f"of consecutive unexcused missed sessions is {consecutive}."
        )

    return MaterialityFinding(
        is_material=pct_fired or run_fired,
        reasons=reasons,
        shortfall_pct=pct,
        max_consecutive_unexcused=consecutive,
        threshold_pct=config.shortfall_pct_threshold,
        threshold_consecutive=config.consecutive_missed_threshold,
        standard_refs=list(config.standard_refs),
    )


def compensatory_estimate(ledger: DeliveryLedger) -> CompensatoryEstimate:
    """A defensible *starting position* for compensatory minutes owed.

    Equal to the unexcused shortfall, but explicitly labeled an equitable
    estimate under Reid v. District of Columbia — not a mechanical entitlement.
    """
    return CompensatoryEstimate(
        commitment_id=ledger.commitment_id,
        estimated_minutes=ledger.unexcused_shortfall_minutes,
        basis="unexcused_shortfall_minutes",
        is_equitable_estimate=True,
        standard_refs=["reid_v_dc"],
    )


# --------------------------------------------------------------------------- #
# Violation detection
# --------------------------------------------------------------------------- #
def _log_ref(log: ServiceLog, service_label: str) -> SourceRef:
    """A click-and-verify reference to a single service-log entry."""
    if log.source_ref is not None:
        return log.source_ref
    return SourceRef(
        kind=SourceKind.SERVICE_LOG,
        locator=log.date.isoformat(),
        description=f"{service_label} session on {log.date.isoformat()} "
                    f"({log.status.value})",
        record_id=log.id,
    )


def _violation_id(commitment_id: str, vtype: ViolationType,
                  start, end) -> str:
    return f"{commitment_id}:{vtype.value}:{start.isoformat()}_{end.isoformat()}"


def detect_violations(
    commitment: ServiceCommitment,
    ledger: DeliveryLedger,
    logs: List[ServiceLog],
    materiality: MaterialityFinding,
) -> List[Violation]:
    """Build the list of typed violations implied by the ledger.

    Minutes-based violations (missed, short) carry the computed materiality
    finding. Quality violations (group dilution, late start) are surfaced with
    their evidence; their materiality is a qualitative judgment left to review.
    """
    window_logs = [
        log for log in logs
        if log.commitment_id == commitment.id
        and ledger.window_start <= log.date <= ledger.window_end
    ]
    service_label = commitment.service_type.value.replace("_", " ")
    iep_ref = commitment.source_ref
    violations: List[Violation] = []

    def _new(vtype: ViolationType, shortfall: int, evidence: List[SourceRef],
             legal_refs: List[str], mat, event_logs: List[ServiceLog] | None = None
             ) -> Violation:
        refs = list(evidence)
        if iep_ref is not None:
            refs.append(iep_ref)
        event_logs = event_logs or []
        event_start = min((log.date for log in event_logs),
                          default=ledger.window_start)
        event_end = max((log.date for log in event_logs),
                        default=ledger.window_end)
        return Violation(
            id=_violation_id(commitment.id, vtype,
                             event_start, event_end),
            commitment_id=commitment.id,
            type=vtype,
            window_start=event_start,
            window_end=event_end,
            shortfall_minutes=shortfall,
            materiality=mat,
            evidence_refs=refs,
            legal_refs=legal_refs,
        )

    # Missed (unexcused) sessions ------------------------------------------------
    if ledger.unexcused_missed_minutes > 0:
        missed_logs = [
            log for log in window_logs
            if log.status == LogStatus.MISSED
            and log.excused == ExcusedClass.UNEXCUSED
        ]
        evidence = [_log_ref(log, service_label) for log in missed_logs]
        violations.append(_new(
            ViolationType.MISSED_SESSIONS,
            ledger.unexcused_missed_minutes,
            evidence,
            ["cfr_300_320", "cfr_300_323", "van_duyn"],
            materiality,
            missed_logs,
        ))

    # Short sessions -------------------------------------------------------------
    if ledger.short_shortfall_minutes > 0:
        short_logs = [
            log for log in window_logs
            if log.status == LogStatus.SHORT
            and log.excused == ExcusedClass.UNEXCUSED
        ]
        evidence = [_log_ref(log, service_label) for log in short_logs]
        violations.append(_new(
            ViolationType.SHORT_SESSIONS,
            ledger.short_shortfall_minutes,
            evidence,
            ["cfr_300_320", "cfr_300_323", "van_duyn"],
            materiality,
            short_logs,
        ))

    # Group dilution -------------------------------------------------------------
    diluted = [
        log for log in window_logs
        if _is_group_dilution(commitment, log)
    ]
    if diluted:
        evidence = [_log_ref(log, service_label) for log in diluted]
        violations.append(_new(
            ViolationType.GROUP_DILUTION,
            0,
            evidence,
            ["cfr_300_320", "cfr_300_323"],
            None,
            diluted,
        ))

    # Late start -----------------------------------------------------------------
    late = _late_start_evidence(commitment, window_logs, service_label)
    if late is not None:
        violations.append(_new(
            ViolationType.LATE_START,
            0,
            [late],
            ["cfr_300_323"],
            None,
        ))

    return violations


def _is_group_dilution(commitment: ServiceCommitment, log: ServiceLog) -> bool:
    """True when a session was delivered in a more diluted setting than promised."""
    # Promised individual, delivered group.
    if (commitment.setting == DeliverySetting.INDIVIDUAL
            and log.setting_actual == DeliverySetting.GROUP):
        return True
    # Group size exceeded the IEP's cap.
    if (commitment.group_size_max is not None
            and log.group_size_actual is not None
            and log.group_size_actual > commitment.group_size_max):
        return True
    return False


def _late_start_evidence(
    commitment: ServiceCommitment,
    window_logs: List[ServiceLog],
    service_label: str,
) -> SourceRef | None:
    """A reference flagging a delayed start of services, if one is evident.

    Services must be in effect at the start of the year with no delay in
    implementation (34 C.F.R. 300.323). If the first actually-delivered session
    is after the commitment's effective start, surface it for review.
    """
    if commitment.effective_start is None:
        return None
    delivered = sorted(
        [log for log in window_logs
         if log.status in (LogStatus.DELIVERED, LogStatus.SHORT)],
        key=lambda x: x.date,
    )
    if not delivered:
        return None
    first = delivered[0]
    if first.date <= commitment.effective_start:
        return None
    days_late = (first.date - commitment.effective_start).days
    return SourceRef(
        kind=SourceKind.SERVICE_LOG,
        locator=first.date.isoformat(),
        description=(
            f"First {service_label} session was {first.date.isoformat()}, "
            f"{days_late} days after the IEP effective start "
            f"{commitment.effective_start.isoformat()}."
        ),
        record_id=first.id,
    )
