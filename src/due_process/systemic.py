"""Systemic evidence — aggregate shortfalls across families into a district case.

One child's complaint documents one child's services. IDEA's state complaint
process can also address appropriate future provision of services and corrective
action (34 C.F.R. 300.151(b)), so patterns across authorized cases can support a
request for broader investigation.

This module aggregates authorized cases **with a privacy gate**: a pattern is
only surfaced when at least ``k`` students share it
(k-anonymity), and findings report counts and minute totals — never an individual
child's record. It turns scattered individual shortfalls into the systemic
evidence that shifts the power asymmetry.

The aggregation is deterministic and operates only on the outputs of the
deterministic ledger, so the systemic claim inherits the same grounding as the
individual ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Tuple

from .analysis import CommitmentAnalysis
from .models import ServiceType

# Minimum students sharing a pattern before it may be reported (k-anonymity).
DEFAULT_K_ANONYMITY = 5
# Share of students with a material failure for the pattern to count as systemic.
DEFAULT_MATERIAL_SHARE_THRESHOLD = Decimal("0.30")


@dataclass
class StudentCase:
    """One de-identified student's analyzed services within a district.

    ``student_id`` is a pseudonym, never a name; it exists only so counts are
    distinct. Callers remain responsible for access control and re-identification
    risk from small or distinctive cohorts.
    """

    student_id: str
    district: str
    analyses: List[CommitmentAnalysis] = field(default_factory=list)


@dataclass
class SystemicFinding:
    """A district-wide pattern for one service type, privacy-gated."""

    district: str
    service_type: ServiceType
    n_students_with_service: int
    n_students_material: int
    material_student_share: Decimal
    total_required_minutes: int
    total_unexcused_minutes: int
    aggregate_shortfall_pct: Decimal
    k_threshold: int
    legal_refs: List[str] = field(default_factory=list)

    @property
    def meets_k_anonymity(self) -> bool:
        return self.n_students_with_service >= self.k_threshold

    @property
    def total_compensatory_minutes(self) -> int:
        # Aggregate comp owed across affected students = aggregate unexcused.
        return self.total_unexcused_minutes


def aggregate_systemic(
    cases: List[StudentCase],
    *,
    k_threshold: int = DEFAULT_K_ANONYMITY,
    material_share_threshold: Decimal = DEFAULT_MATERIAL_SHARE_THRESHOLD,
) -> List[SystemicFinding]:
    """Aggregate per-student analyses into privacy-gated systemic findings.

    Returns only patterns that (a) meet k-anonymity (>= ``k_threshold`` students
    receive the service) and (b) are genuinely systemic (>= ``material_share_
    threshold`` of those students have a material failure). Patterns below the
    k-anonymity floor are suppressed entirely — they cannot be reported without
    risking re-identification.
    """
    groups: Dict[Tuple[str, ServiceType], List[CommitmentAnalysis]] = {}
    for case in cases:
        for analysis in case.analyses:
            key = (case.district, analysis.commitment.service_type)
            groups.setdefault(key, []).append(analysis)

    findings: List[SystemicFinding] = []
    for (district, service_type), analyses in groups.items():
        n = len(analyses)
        n_material = sum(1 for a in analyses if a.materiality.is_material)
        total_required = sum(a.ledger.required_minutes for a in analyses)
        total_unexcused = sum(
            a.ledger.unexcused_shortfall_minutes for a in analyses)
        share = Decimal(n_material) / Decimal(n) if n else Decimal(0)
        agg_pct = (Decimal(total_unexcused) / Decimal(total_required)
                   if total_required else Decimal(0))

        finding = SystemicFinding(
            district=district,
            service_type=service_type,
            n_students_with_service=n,
            n_students_material=n_material,
            material_student_share=share,
            total_required_minutes=total_required,
            total_unexcused_minutes=total_unexcused,
            aggregate_shortfall_pct=agg_pct,
            k_threshold=k_threshold,
            legal_refs=["cfr_300_151_153", "cfr_300_323", "van_duyn"],
        )
        if finding.meets_k_anonymity and share >= material_share_threshold:
            findings.append(finding)

    # Most-affected first.
    findings.sort(key=lambda f: f.aggregate_shortfall_pct, reverse=True)
    return findings


def suppressed_groups(
    cases: List[StudentCase],
    *,
    k_threshold: int = DEFAULT_K_ANONYMITY,
) -> List[Tuple[str, ServiceType, int]]:
    """Patterns withheld for privacy (below k-anonymity).

    Surfaced so the suppression is transparent rather than silent — a small
    cohort is not evidence of nothing, it is just not safe to report.
    """
    groups: Dict[Tuple[str, ServiceType], int] = {}
    for case in cases:
        for analysis in case.analyses:
            key = (case.district, analysis.commitment.service_type)
            groups[key] = groups.get(key, 0) + 1
    return [(d, s, n) for (d, s), n in groups.items() if n < k_threshold]
