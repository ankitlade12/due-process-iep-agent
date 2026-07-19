"""Domain model for the IEP enforcement agent.

These dataclasses mirror the spec's data model one-to-one. They are plain data —
no behavior, no LLM, no I/O — so they can be constructed and asserted on in unit
tests, serialized to the PostgreSQL ledger, and handed to the deterministic
engines (:mod:`due_process.ledger`, :mod:`due_process.materiality`,
:mod:`due_process.deadlines`, :mod:`due_process.pwn`).

Enums subclass ``str`` so they serialize cleanly to JSON and compare equal to the
raw strings the LLM extraction layer will produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class ServiceType(str, Enum):
    """The kinds of related/special-education services an IEP commits to.

    The hackathon scope focuses on services with the cleanest minutes model
    (speech, OT, PT); the rest are included so real IEPs parse without loss.
    """

    SPEECH_LANGUAGE = "speech_language"
    OCCUPATIONAL_THERAPY = "occupational_therapy"
    PHYSICAL_THERAPY = "physical_therapy"
    COUNSELING = "counseling"
    SPECIALIZED_INSTRUCTION = "specialized_instruction"
    BEHAVIORAL_SUPPORT = "behavioral_support"
    OTHER = "other"


class FrequencyPeriod(str, Enum):
    """The denominator of a service frequency (e.g. 3x per *week*)."""

    WEEK = "week"
    MONTH = "month"


class DeliverySetting(str, Enum):
    """Individual vs group delivery. ``GROUP`` past ``group_size_max`` dilutes
    the service and is a violation type of its own."""

    INDIVIDUAL = "individual"
    GROUP = "group"


class ServiceLocation(str, Enum):
    """Pull-out (separate setting) vs push-in (in the general classroom)."""

    PULL_OUT = "pull_out"
    PUSH_IN = "push_in"


class LogStatus(str, Enum):
    """How a single scheduled session actually went."""

    DELIVERED = "delivered"   # full required minutes delivered
    SHORT = "short"           # delivered, but fewer minutes than required
    MISSED = "missed"         # not delivered at all


class ExcusedClass(str, Enum):
    """Whether a missed/short session counts against the school.

    Set by the bounded LLM classifier and/or a human. ``AMBIGUOUS`` is never
    auto-resolved — it is routed to a human checkpoint.
    """

    EXCUSED = "excused"        # child absence, fire drill later made up, etc.
    UNEXCUSED = "unexcused"    # provider absence, no substitute, scheduling
    AMBIGUOUS = "ambiguous"    # flagged for human review
    UNCLASSIFIED = "unclassified"  # not yet looked at


class ViolationType(str, Enum):
    """The kinds of IEP-implementation failure the agent can detect."""

    MISSED_SESSIONS = "missed_sessions"
    SHORT_SESSIONS = "short_sessions"
    GROUP_DILUTION = "group_dilution"
    WRONG_PROVIDER = "wrong_provider"
    LATE_START = "late_start"
    UNIMPLEMENTED_ACCOMMODATION = "unimplemented_accommodation"


class ViolationStatus(str, Enum):
    """Lifecycle of a detected violation."""

    OPEN = "open"
    RESOLVED_BY_MAKEUP = "resolved_by_makeup"
    ESCALATED = "escalated"


class InstrumentType(str, Enum):
    """The outbound documents the agent can draft, lowest to highest friction."""

    SERVICE_LOG_REQUEST = "service_log_request"
    PWN_REQUEST = "pwn_request"
    IEE_REQUEST = "iee_request"
    STATE_COMPLAINT = "state_complaint"
    SYSTEMIC_COMPLAINT = "systemic_complaint"
    DUE_PROCESS = "due_process"
    MEDIATION_REQUEST = "mediation_request"


class InstrumentStatus(str, Enum):
    """Approval lifecycle of a drafted instrument."""

    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"


class SourceKind(str, Enum):
    """What a piece of evidence is, for the grounding layer."""

    IEP = "iep"
    SERVICE_LOG = "service_log"
    PARENT_INPUT = "parent_input"
    PWN = "pwn"
    REGULATION = "regulation"
    CALENDAR = "calendar"


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #
@dataclass
class SourceRef:
    """A verifiable pointer to a piece of evidence — the click-and-check link.

    Every assertion the system makes carries one or more of these so a parent
    (or a hearing officer) can verify it against the original document.
    """

    kind: SourceKind
    locator: str = ""          # e.g. "p.7 §Services", "log row 42", "2026-03-04"
    description: str = ""       # human-readable summary of what is there
    uri: str = ""              # clickable source link (eCFR URL, record URI, ...)
    record_id: str = ""        # id of the underlying ServiceLog/ServiceCommitment

    def cite(self) -> str:
        """Short citation string for letters and the UI."""
        head = self.description or self.kind.value
        return f"{head} ({self.locator})" if self.locator else head


# --------------------------------------------------------------------------- #
# Core entities (parsed / ingested)
# --------------------------------------------------------------------------- #
@dataclass
class ServiceCommitment:
    """One service the IEP promises, parsed from the services page.

    Source for parsing is 34 C.F.R. 300.320 (IEP content, including frequency,
    duration, and location of services).
    """

    id: str
    service_type: ServiceType
    frequency_count: int                 # e.g. 3 (sessions)
    frequency_period: FrequencyPeriod    # ... per WEEK
    duration_minutes: int                # ... of 30 minutes each
    setting: DeliverySetting = DeliverySetting.INDIVIDUAL
    location: Optional[ServiceLocation] = None
    group_size_max: Optional[int] = None
    provider_qualification: str = ""     # e.g. "licensed SLP"
    linked_goal_ids: List[str] = field(default_factory=list)
    effective_start: Optional[date] = None
    effective_end: Optional[date] = None
    source_ref: Optional[SourceRef] = None

    def required_minutes_per_period(self) -> int:
        return self.frequency_count * self.duration_minutes


@dataclass
class ServiceLog:
    """One scheduled session as actually recorded — by the school or the parent."""

    id: str
    commitment_id: str
    date: date
    minutes_delivered: int = 0
    status: LogStatus = LogStatus.DELIVERED
    setting_actual: Optional[DeliverySetting] = None
    group_size_actual: Optional[int] = None
    provider: str = ""
    missed_reason_text: str = ""
    excused: ExcusedClass = ExcusedClass.UNCLASSIFIED
    source_ref: Optional[SourceRef] = None
    # When set, this (delivered) session makes up for the missed session with
    # this id — resolving that shortfall rather than adding a new one.
    makeup_for: Optional[str] = None


# --------------------------------------------------------------------------- #
# Computed artifacts
# --------------------------------------------------------------------------- #
@dataclass
class DeliveryLedger:
    """Deterministic promised-vs-delivered tally for one commitment over a window.

    Produced by :func:`due_process.ledger.compute_ledger`. Every field is an
    auditable integer count or minute total; no field is an LLM guess.
    """

    commitment_id: str
    window_start: date
    window_end: date

    required_sessions: int
    required_minutes: int

    delivered_sessions: int
    delivered_minutes: int

    excused_sessions: int
    excused_minutes: int

    unexcused_missed_sessions: int
    unexcused_missed_minutes: int

    short_sessions: int
    short_shortfall_minutes: int

    unlogged_sessions: int
    unlogged_minutes: int

    # Missed/short minutes awaiting a human excused/unexcused call. Held out of
    # the actionable shortfall — the human-in-the-loop guard, never auto-resolved.
    ambiguous_sessions: int = 0
    ambiguous_minutes: int = 0

    # Missed minutes the school later made up — cured, so no longer owed.
    resolved_by_makeup_sessions: int = 0
    resolved_by_makeup_minutes: int = 0

    @property
    def unexcused_shortfall_minutes(self) -> int:
        """The number that drives materiality: minutes owed the school cannot
        excuse. Excludes unlogged (unknown) and ambiguous (pending) minutes."""
        return self.unexcused_missed_minutes + self.short_shortfall_minutes

    @property
    def shortfall_pct(self) -> Decimal:
        """Unexcused shortfall as a share of required minutes (0..1)."""
        if self.required_minutes <= 0:
            return Decimal(0)
        return (Decimal(self.unexcused_shortfall_minutes)
                / Decimal(self.required_minutes))

    @property
    def logs_complete(self) -> bool:
        """True when every required session has a corresponding log entry.
        When False, the first instrument is a service-log request, not a
        complaint — you cannot prove a shortfall you have not yet documented."""
        return self.unlogged_sessions == 0


@dataclass
class MaterialityFinding:
    """The deterministic materiality verdict plus an optional LLM rationale.

    The boolean and the triggering facts are computed by code. ``llm_rationale``
    is plain-language narration added later and is never load-bearing.
    """

    is_material: bool
    reasons: List[str] = field(default_factory=list)
    shortfall_pct: Decimal = Decimal(0)
    max_consecutive_unexcused: int = 0
    threshold_pct: Decimal = Decimal(0)
    threshold_consecutive: int = 0
    standard_refs: List[str] = field(default_factory=list)  # corpus ids
    llm_rationale: str = ""


@dataclass
class Violation:
    """A detected, classified shortfall — the unit a complaint is built from."""

    id: str
    commitment_id: str
    type: ViolationType
    window_start: date
    window_end: date
    shortfall_minutes: int
    materiality: Optional[MaterialityFinding] = None
    evidence_refs: List[SourceRef] = field(default_factory=list)
    legal_refs: List[str] = field(default_factory=list)  # corpus provision ids
    status: ViolationStatus = ViolationStatus.OPEN


@dataclass
class DeadlineClock:
    """The statute-of-limitations clock for a violation.

    ``sol_expiry_date`` is ``discovery_date`` plus the state's limitations period
    (federal default: two years unless state law supplies an explicit alternative,
    20 U.S.C. 1415(b)(6),(f)(3)(C)).
    """

    violation_id: str
    discovery_date: date          # the date the clock runs from (anchor)
    sol_expiry_date: date
    days_remaining: int
    state: str = ""
    limitations_years: int = 2
    remedy: str = "due_process"   # "state_complaint" (1 yr) | "due_process" (2 yr)
    basis: str = "usc_1415_sol"   # corpus id grounding this deadline


@dataclass
class CompensatoryEstimate:
    """A defensible *starting position* for compensatory services owed.

    Per Reid v. District of Columbia, comp education is a flexible equitable
    remedy, not a mechanical hour-for-hour entitlement — so this is labeled an
    estimate, not a guarantee.
    """

    commitment_id: str
    estimated_minutes: int
    basis: str = "unexcused_shortfall_minutes"
    is_equitable_estimate: bool = True
    standard_refs: List[str] = field(default_factory=list)  # e.g. ["reid_v_dc"]
    note: str = (
        "Equitable starting position under Reid v. District of Columbia; the "
        "actual award is fact-specific and subject to a qualitative analysis."
    )


@dataclass
class Instrument:
    """A drafted outbound document, gated behind human approval before sending."""

    type: InstrumentType
    violation_ids: List[str] = field(default_factory=list)
    draft_text: str = ""
    citations: List[str] = field(default_factory=list)  # corpus provision ids
    status: InstrumentStatus = InstrumentStatus.DRAFT
    sent_timestamp: Optional[datetime] = None
