"""Prior Written Notice (PWN) compliance checklist — 34 C.F.R. 300.503(b).

When a school proposes or refuses to change a child's identification,
evaluation, placement, or FAPE, it must give the parent Prior Written Notice
containing seven specific elements. This module encodes those seven elements and
the compliance verdict **deterministically**: given which elements are present,
it decides compliance and lists what is missing, and cites 34 C.F.R. 300.503.

Detecting whether a given element actually appears in a particular PWN document
is a bounded extraction task handled by the LLM layer; that layer feeds its
per-element present/absent calls into :func:`evaluate_pwn`, which owns the law
and the verdict. The split keeps the legal logic auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import SourceRef

PWN_CITATION = "cfr_300_503"


@dataclass(frozen=True)
class PwnElement:
    """One of the seven required PWN elements."""

    number: int            # 1..7, matching 34 C.F.R. 300.503(b)(1)..(7)
    key: str
    subsection: str        # e.g. "34 C.F.R. 300.503(b)(1)"
    description: str


# The seven elements, in regulatory order, 34 C.F.R. 300.503(b)(1)-(7).
PWN_ELEMENTS: List[PwnElement] = [
    PwnElement(
        1, "action_described", "34 C.F.R. 300.503(b)(1)",
        "A description of the action proposed or refused by the agency.",
    ),
    PwnElement(
        2, "explanation", "34 C.F.R. 300.503(b)(2)",
        "An explanation of why the agency proposes or refuses to take the action.",
    ),
    PwnElement(
        3, "basis", "34 C.F.R. 300.503(b)(3)",
        "A description of each evaluation procedure, assessment, record, or "
        "report the agency used as a basis for the proposed or refused action.",
    ),
    PwnElement(
        4, "safeguards", "34 C.F.R. 300.503(b)(4)",
        "A statement that the parents of a child with a disability have "
        "protection under the procedural safeguards and, if this notice is not "
        "an initial referral for evaluation, the means by which a copy of the "
        "safeguards can be obtained.",
    ),
    PwnElement(
        5, "assistance_sources", "34 C.F.R. 300.503(b)(5)",
        "Sources for parents to contact to obtain assistance in understanding "
        "the provisions of this part.",
    ),
    PwnElement(
        6, "options_considered", "34 C.F.R. 300.503(b)(6)",
        "A description of other options the IEP Team considered and the reasons "
        "those options were rejected.",
    ),
    PwnElement(
        7, "other_factors", "34 C.F.R. 300.503(b)(7)",
        "A description of other factors relevant to the agency's proposal or "
        "refusal.",
    ),
]

_BY_NUMBER: Dict[int, PwnElement] = {e.number: e for e in PWN_ELEMENTS}
_BY_KEY: Dict[str, PwnElement] = {e.key: e for e in PWN_ELEMENTS}


@dataclass
class PwnElementResult:
    """Per-element finding: was this required element present in the PWN?"""

    element: PwnElement
    present: bool
    evidence_ref: Optional[SourceRef] = None
    note: str = ""


@dataclass
class PwnChecklistResult:
    """The overall PWN compliance verdict."""

    compliant: bool
    results: List[PwnElementResult] = field(default_factory=list)
    citation: str = PWN_CITATION

    @property
    def missing(self) -> List[PwnElement]:
        return [r.element for r in self.results if not r.present]

    @property
    def present(self) -> List[PwnElement]:
        return [r.element for r in self.results if r.present]

    def summary(self) -> str:
        if self.compliant:
            return "PWN contains all seven required elements (34 C.F.R. 300.503(b))."
        missing = self.missing
        nums = ", ".join(f"(b)({e.number})" for e in missing)
        return (
            f"PWN is missing {len(missing)} of 7 required elements "
            f"under 34 C.F.R. 300.503(b): {nums}."
        )


def _resolve(key) -> PwnElement:
    """Resolve an element by 1..7 number or by string key."""
    if isinstance(key, int):
        if key not in _BY_NUMBER:
            raise KeyError(f"PWN element number must be 1..7, got {key}")
        return _BY_NUMBER[key]
    if key in _BY_KEY:
        return _BY_KEY[key]
    raise KeyError(f"Unknown PWN element key {key!r}; "
                   f"known keys: {sorted(_BY_KEY)}")


def evaluate_pwn(
    present_by_element: Dict,
    evidence_by_element: Optional[Dict] = None,
) -> PwnChecklistResult:
    """Evaluate a PWN's compliance from per-element present/absent calls.

    Args:
        present_by_element: maps an element number (1..7) or key to a bool
            indicating whether that element is present in the PWN. Elements
            omitted from the mapping are treated as absent.
        evidence_by_element: optional map (same keys) to a SourceRef pointing at
            where the element appears in the document.

    Returns:
        A :class:`PwnChecklistResult`. ``compliant`` is True only when all seven
        elements are present.
    """
    evidence_by_element = evidence_by_element or {}

    # Normalize caller keys (numbers or strings) onto element numbers.
    present_norm: Dict[int, bool] = {}
    evidence_norm: Dict[int, SourceRef] = {}
    for key, value in present_by_element.items():
        present_norm[_resolve(key).number] = bool(value)
    for key, value in evidence_by_element.items():
        evidence_norm[_resolve(key).number] = value

    results: List[PwnElementResult] = []
    for element in PWN_ELEMENTS:
        present = present_norm.get(element.number, False)
        results.append(PwnElementResult(
            element=element,
            present=present,
            evidence_ref=evidence_norm.get(element.number),
            note="" if present else "Required element not found in the PWN.",
        ))

    compliant = all(r.present for r in results)
    return PwnChecklistResult(compliant=compliant, results=results)
