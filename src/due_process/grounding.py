"""Grounding by evidence ID.

Every flagged violation links to three things a parent can click and verify:

  1. the IEP provision (page and section),
  2. the service-log entry/entries that show the shortfall,
  3. the governing IDEA / state regulation that defines the standard.

This module assembles those links into an :class:`EvidenceBundle` and enforces
two invariants that make hallucination impossible *by construction*:

  * every legal citation must resolve to a real entry in
    :mod:`due_process.corpus` (no inventing a standard), and
  * a minutes-based violation must point at the actual log entries the
    deterministic ledger counted (no inventing a shortfall).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from . import corpus
from .corpus import LegalProvision
from .models import SourceKind, SourceRef, Violation, ViolationType

# Violation types whose claim is a number of minutes — these must cite at least
# one underlying service-log entry, or the shortfall is unsupported.
_MINUTES_BASED = {ViolationType.MISSED_SESSIONS, ViolationType.SHORT_SESSIONS}


@dataclass
class EvidenceBundle:
    """The three grounding buckets for a single violation."""

    violation_id: str
    iep_refs: List[SourceRef] = field(default_factory=list)
    log_refs: List[SourceRef] = field(default_factory=list)
    other_refs: List[SourceRef] = field(default_factory=list)
    legal_provisions: List[LegalProvision] = field(default_factory=list)

    def is_complete(self) -> bool:
        """A bundle is complete when it has a legal basis and a factual anchor."""
        return bool(self.legal_provisions) and bool(self.iep_refs or self.log_refs)

    def to_markdown(self) -> str:
        """Render the bundle as a clickable evidence block for letters / UI."""
        lines: List[str] = []
        if self.iep_refs:
            lines.append("**IEP provision**")
            lines += [f"- {_ref_md(r)}" for r in self.iep_refs]
        if self.log_refs:
            lines.append("**Service-log evidence**")
            lines += [f"- {_ref_md(r)}" for r in self.log_refs]
        if self.legal_provisions:
            lines.append("**Governing law**")
            for p in self.legal_provisions:
                suffix = " *(verify against primary source)*" if p.verify_required else ""
                link = f"[{p.short_label}]({p.url})" if p.url else p.short_label
                lines.append(f"- {link} — {p.governs}{suffix}")
        return "\n".join(lines)


def _ref_md(ref: SourceRef) -> str:
    text = ref.cite()
    return f"[{text}]({ref.uri})" if ref.uri else text


class GroundingError(ValueError):
    """Raised when a violation is not properly grounded."""


def verify_citations(provision_ids: List[str]) -> List[LegalProvision]:
    """Resolve and validate citation ids against the corpus.

    Raises :class:`KeyError` (via the corpus) if any id is not a real provision —
    the guard that prevents citing a legal standard that does not exist.
    """
    corpus.validate_refs(provision_ids)
    return [corpus.get(pid) for pid in provision_ids]


def build_evidence_bundle(violation: Violation) -> EvidenceBundle:
    """Assemble and validate the evidence bundle for a violation."""
    legal_provisions = verify_citations(violation.legal_refs)

    iep_refs: List[SourceRef] = []
    log_refs: List[SourceRef] = []
    other_refs: List[SourceRef] = []
    for ref in violation.evidence_refs:
        if ref.kind == SourceKind.IEP:
            iep_refs.append(ref)
        elif ref.kind in (SourceKind.SERVICE_LOG, SourceKind.PARENT_INPUT):
            log_refs.append(ref)
        else:
            other_refs.append(ref)

    return EvidenceBundle(
        violation_id=violation.id,
        iep_refs=iep_refs,
        log_refs=log_refs,
        other_refs=other_refs,
        legal_provisions=legal_provisions,
    )


def assert_grounded(violation: Violation) -> EvidenceBundle:
    """Validate a violation is fully grounded, returning its bundle.

    Enforces the two structural invariants. Use this as the gate before any
    violation is shown to a parent or written into an instrument.
    """
    bundle = build_evidence_bundle(violation)

    if not bundle.legal_provisions:
        raise GroundingError(
            f"Violation {violation.id} cites no legal standard; "
            "every claim must be grounded to the corpus."
        )

    if violation.type in _MINUTES_BASED and not bundle.log_refs:
        raise GroundingError(
            f"Violation {violation.id} asserts a {violation.shortfall_minutes}-"
            "minute shortfall but cites no service-log evidence; the ledger must "
            "support every minute claimed."
        )

    return bundle
