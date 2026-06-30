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

from .deadlines import compute_deadline_for_violation
from .grounding import EvidenceBundle, build_evidence_bundle
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
    deadlines: List[DeadlineClock] = field(default_factory=list)
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
    deadlines = [
        compute_deadline_for_violation(
            v, today, discovery_date=discovery_date, state=state
        )
        for v in violations
    ]
    bundles = [build_evidence_bundle(v) for v in violations]

    return CommitmentAnalysis(
        commitment=commitment,
        ledger=ledger,
        materiality=materiality,
        violations=violations,
        compensatory=compensatory,
        deadlines=deadlines,
        bundles=bundles,
    )
