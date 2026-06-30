"""Tests for the grounding / evidence-by-ID layer."""

from datetime import date

import pytest

from due_process.grounding import (
    GroundingError,
    assert_grounded,
    build_evidence_bundle,
    verify_citations,
)
from due_process.models import (
    SourceKind,
    SourceRef,
    Violation,
    ViolationType,
)


def _violation(legal_refs, evidence_refs, vtype=ViolationType.MISSED_SESSIONS):
    return Violation(
        id="v1",
        commitment_id="c1",
        type=vtype,
        window_start=date(2025, 9, 1),
        window_end=date(2026, 5, 30),
        shortfall_minutes=720,
        evidence_refs=evidence_refs,
        legal_refs=legal_refs,
    )


def test_verify_citations_resolves_known():
    provisions = verify_citations(["cfr_300_323", "van_duyn"])
    assert len(provisions) == 2


def test_verify_citations_rejects_hallucination():
    with pytest.raises(KeyError):
        verify_citations(["cfr_300_323", "totally_made_up"])


def test_bundle_partitions_refs():
    refs = [
        SourceRef(kind=SourceKind.IEP, locator="p.7"),
        SourceRef(kind=SourceKind.SERVICE_LOG, locator="row 3"),
        SourceRef(kind=SourceKind.SERVICE_LOG, locator="row 4"),
    ]
    v = _violation(["cfr_300_323", "van_duyn"], refs)
    bundle = build_evidence_bundle(v)
    assert len(bundle.iep_refs) == 1
    assert len(bundle.log_refs) == 2
    assert len(bundle.legal_provisions) == 2
    assert bundle.is_complete() is True


def test_assert_grounded_passes_for_well_formed_violation():
    refs = [
        SourceRef(kind=SourceKind.IEP, locator="p.7"),
        SourceRef(kind=SourceKind.SERVICE_LOG, locator="row 3"),
    ]
    bundle = assert_grounded(_violation(["cfr_300_323"], refs))
    assert bundle.is_complete()


def test_assert_grounded_rejects_missing_legal_basis():
    refs = [SourceRef(kind=SourceKind.SERVICE_LOG, locator="row 3")]
    with pytest.raises(GroundingError):
        assert_grounded(_violation([], refs))


def test_assert_grounded_rejects_minutes_claim_without_logs():
    # A missed-sessions violation must point at the actual log entries.
    refs = [SourceRef(kind=SourceKind.IEP, locator="p.7")]
    with pytest.raises(GroundingError):
        assert_grounded(_violation(["cfr_300_323"], refs))


def test_markdown_renders_links():
    refs = [
        SourceRef(kind=SourceKind.IEP, locator="p.7", description="Speech line",
                  uri="oss://iep.pdf#7"),
        SourceRef(kind=SourceKind.SERVICE_LOG, locator="row 3",
                  description="Log row 3"),
    ]
    md = build_evidence_bundle(_violation(["cfr_300_323"], refs)).to_markdown()
    assert "Governing law" in md
    assert "300.323" in md
    assert "oss://iep.pdf#7" in md
