"""The deterministic analysis pipeline.

Ties the core engines together into the single call the agent makes per
commitment: compute the ledger, apply the materiality rule, detect and ground
the violations, estimate compensatory time, and start the deadline clock. Every
step is deterministic; the LLM layer sits *outside* this function and only
prepares its inputs (classified logs) and narrates its outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .deadlines import due_process_deadline, state_complaint_deadline
from .grounding import EvidenceBundle, assert_grounded
from .ledger import compute_ledger
from .materiality import (
    DEFAULT_CONFIG,
    MaterialityConfig,
    classify_materiality,
    compensatory_estimate,
    detect_violations,
)
from .models import (
    CompensatoryEstimate,
    DeadlineClock,
    DeliveryLedger,
    MaterialityFinding,
    ServiceCommitment,
    ServiceLog,
    Violation,
)


@dataclass
class CommitmentAnalysis:
    """The full deterministic finding for one service commitment over a window."""

    commitment: ServiceCommitment
    ledger: DeliveryLedger
    materiality: MaterialityFinding
    violations: List[Violation] = field(default_factory=list)
    compensatory: Optional[CompensatoryEstimate] = None
    deadlines: List[DeadlineClock] = field(default_factory=list)  # state complaint (1 yr)
    due_process_deadlines: List[DeadlineClock] = field(default_factory=list)  # 2 yr
    bundles: List[EvidenceBundle] = field(default_factory=list)

    @property
    def has_actionable_violation(self) -> bool:
        return self.materiality.is_material and bool(self.violations)

    @property
    def needs_logs_first(self) -> bool:
        """True when logs are incomplete — request logs before any complaint."""
        return not self.ledger.logs_complete


def analyze_commitment(
    commitment: ServiceCommitment,
    logs: List[ServiceLog],
    *,
    window_start: date,
    window_end: date,
    today: date,
    required_sessions: Optional[int] = None,
    instructional_periods: Optional[int] = None,
    discovery_date: Optional[date] = None,
    state: str = "",
    config: MaterialityConfig = DEFAULT_CONFIG,
) -> CommitmentAnalysis:
    """Run the deterministic pipeline for a single commitment."""
    ledger = compute_ledger(
        commitment,
        logs,
        window_start=window_start,
        window_end=window_end,
        required_sessions=required_sessions,
        instructional_periods=instructional_periods,
    )
    materiality = classify_materiality(ledger, logs, config)
    violations = detect_violations(commitment, ledger, logs, materiality)
    compensatory = compensatory_estimate(ledger)
    # Two distinct clocks per violation. The state-complaint deadline (1 year
    # from the violation, 34 C.F.R. 300.153(c)) is primary because the tool's
    # default instrument is a state complaint; the due-process deadline (2 years)
    # is the alternative. The window start is the conservative anchor — the
    # earliest point the window's violations could have occurred.
    deadlines = []
    due_process_deadlines = []
    for v in violations:
        deadlines.append(
            state_complaint_deadline(v.id, v.window_start, today, state=state))
        dp_anchor = discovery_date if discovery_date is not None else v.window_end
        due_process_deadlines.append(
            due_process_deadline(v.id, dp_anchor, today, state=state))
    # This is the publication gate: a complaint cannot consume a violation
    # unless the factual evidence and legal authority both validate.
    bundles = [assert_grounded(v) for v in violations]

    return CommitmentAnalysis(
        commitment=commitment,
        ledger=ledger,
        materiality=materiality,
        violations=violations,
        compensatory=compensatory,
        deadlines=deadlines,
        due_process_deadlines=due_process_deadlines,
        bundles=bundles,
    )
