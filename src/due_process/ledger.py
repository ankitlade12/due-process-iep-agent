"""The deterministic delivery ledger — promised minutes vs delivered minutes.

This is the hard center of the system. It does pure integer arithmetic over a
service commitment and its logs and produces an auditable
:class:`~due_process.models.DeliveryLedger`. **No LLM is involved.** The only
"soft" input is each log's ``excused`` classification, which is produced upstream
by the bounded LLM classifier *and confirmed by a human*; this module just sums
according to that classification.

The accounting, per scheduled session, splits the *gap* between required and
delivered minutes into one of four buckets:

  * delivered      — minutes actually provided
  * excused        — gap the school is not responsible for (child absence, ...)
  * unexcused      — gap that counts against the school (provider absence, ...)
  * pending        — gap whose excused/unexcused status a human has not confirmed

Plus a fifth, *unlogged*: required sessions with no log entry at all. When any
sessions are unlogged the logs are incomplete, and the correct first instrument
is a service-log request — you cannot prove a shortfall you have not documented.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from .models import (
    DeliveryLedger,
    ExcusedClass,
    LogStatus,
    ServiceCommitment,
    ServiceLog,
)


def required_sessions_for(commitment: ServiceCommitment, periods: int) -> int:
    """Required session count = frequency per period × number of periods.

    ``periods`` is the number of *instructional* periods in the window (e.g. 36
    instructional weeks in a school year), taken from the school calendar — not
    every calendar week is an instructional week.
    """
    if periods < 0:
        raise ValueError("periods must be non-negative")
    return commitment.frequency_count * periods


def _logs_in_window(
    logs: List[ServiceLog],
    commitment_id: str,
    window_start: date,
    window_end: date,
) -> List[ServiceLog]:
    """Logs belonging to this commitment and falling within [start, end]."""
    return [
        log
        for log in logs
        if log.commitment_id == commitment_id
        and window_start <= log.date <= window_end
    ]


def compute_ledger(
    commitment: ServiceCommitment,
    logs: List[ServiceLog],
    *,
    window_start: date,
    window_end: date,
    required_sessions: Optional[int] = None,
    instructional_periods: Optional[int] = None,
) -> DeliveryLedger:
    """Compute the deterministic delivery ledger for one commitment.

    Provide the required session count either directly via ``required_sessions``
    or as ``instructional_periods`` (multiplied by the commitment's frequency).

    Args:
        commitment: the parsed IEP service commitment.
        logs: service logs (this commitment's and possibly others'; filtered).
        window_start / window_end: inclusive date bounds of the analysis window.
        required_sessions: total sessions the IEP required over the window.
        instructional_periods: alternative to ``required_sessions``.

    Returns:
        A :class:`DeliveryLedger` whose every field is an auditable integer.
    """
    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start")

    if required_sessions is None:
        if instructional_periods is None:
            raise ValueError(
                "provide either required_sessions or instructional_periods"
            )
        required_sessions = required_sessions_for(commitment, instructional_periods)
    if required_sessions < 0:
        raise ValueError("required_sessions must be non-negative")

    duration = commitment.duration_minutes
    if duration < 0:
        raise ValueError("commitment.duration_minutes must be non-negative")

    required_minutes = required_sessions * duration

    window_logs = _logs_in_window(
        logs, commitment.id, window_start, window_end
    )
    # A make-up session (makeup_for set) is not a scheduled session; it cures a
    # prior miss. Separate the two, and tally make-up minutes per missed session.
    makeup_logs = [lg for lg in window_logs if lg.makeup_for]
    scheduled_logs = [lg for lg in window_logs if not lg.makeup_for]
    makeup_minutes_by_miss: dict = {}
    for ml in makeup_logs:
        makeup_minutes_by_miss[ml.makeup_for] = (
            makeup_minutes_by_miss.get(ml.makeup_for, 0)
            + max(0, ml.minutes_delivered))

    delivered_sessions = 0
    delivered_minutes = 0
    excused_sessions = 0
    excused_minutes = 0
    unexcused_missed_sessions = 0
    unexcused_missed_minutes = 0
    short_sessions = 0
    short_shortfall_minutes = 0
    ambiguous_sessions = 0
    ambiguous_minutes = 0
    resolved_by_makeup_sessions = 0
    resolved_by_makeup_minutes = 0

    for log in scheduled_logs:
        delivered = max(0, log.minutes_delivered)
        delivered_minutes += delivered
        # The gap is what the IEP required for this session but did not get.
        gap = max(0, duration - delivered)

        if log.status == LogStatus.DELIVERED:
            delivered_sessions += 1
            # A fully delivered session has no gap to allocate (gap is ~0).
            if gap == 0:
                continue
        elif log.status == LogStatus.SHORT:
            short_sessions += 1
        # MISSED sessions contribute their whole duration as the gap.

        # A later make-up session cures part or all of this shortfall.
        available = makeup_minutes_by_miss.get(log.id, 0)
        if gap > 0 and available > 0:
            resolved_here = min(gap, available)
            resolved_by_makeup_minutes += resolved_here
            resolved_by_makeup_sessions += 1
            gap -= resolved_here
            if gap == 0:
                continue

        # Allocate the remaining gap by the human-confirmed classification.
        if log.excused == ExcusedClass.EXCUSED:
            excused_minutes += gap
            if log.status == LogStatus.MISSED:
                excused_sessions += 1
        elif log.excused == ExcusedClass.UNEXCUSED:
            if log.status == LogStatus.MISSED:
                unexcused_missed_sessions += 1
                unexcused_missed_minutes += gap
            else:  # SHORT (or a DELIVERED-but-incomplete session)
                short_shortfall_minutes += gap
        else:  # AMBIGUOUS or UNCLASSIFIED — never auto-resolved
            ambiguous_sessions += 1
            ambiguous_minutes += gap

    unlogged_sessions = max(0, required_sessions - len(scheduled_logs))
    unlogged_minutes = unlogged_sessions * duration

    return DeliveryLedger(
        commitment_id=commitment.id,
        window_start=window_start,
        window_end=window_end,
        required_sessions=required_sessions,
        required_minutes=required_minutes,
        delivered_sessions=delivered_sessions,
        delivered_minutes=delivered_minutes,
        excused_sessions=excused_sessions,
        excused_minutes=excused_minutes,
        unexcused_missed_sessions=unexcused_missed_sessions,
        unexcused_missed_minutes=unexcused_missed_minutes,
        short_sessions=short_sessions,
        short_shortfall_minutes=short_shortfall_minutes,
        unlogged_sessions=unlogged_sessions,
        unlogged_minutes=unlogged_minutes,
        ambiguous_sessions=ambiguous_sessions,
        ambiguous_minutes=ambiguous_minutes,
        resolved_by_makeup_sessions=resolved_by_makeup_sessions,
        resolved_by_makeup_minutes=resolved_by_makeup_minutes,
    )


def accounting_residual(ledger: DeliveryLedger) -> int:
    """Cross-check: required minutes minus every allocated bucket.

    For a complete, fully-classified ledger with no make-up sessions this is
    exactly zero — required = delivered + excused + unexcused + pending +
    unlogged. A non-zero residual flags an accounting inconsistency worth
    surfacing (e.g. make-up sessions delivered beyond the scheduled count).
    """
    allocated = (
        ledger.delivered_minutes
        + ledger.excused_minutes
        + ledger.unexcused_shortfall_minutes
        + ledger.ambiguous_minutes
        + ledger.resolved_by_makeup_minutes
        + ledger.unlogged_minutes
    )
    return ledger.required_minutes - allocated
