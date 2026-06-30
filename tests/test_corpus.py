"""Tests for the legal grounding corpus."""

import pytest

from due_process import corpus
from due_process.corpus import AuthorityKind


def test_known_provision_resolves():
    p = corpus.get("cfr_300_323")
    assert "300.323" in p.short_label
    assert p.kind == AuthorityKind.REGULATION


def test_unknown_provision_raises():
    with pytest.raises(KeyError):
        corpus.get("cfr_999_999")


def test_validate_refs_passes_for_known():
    corpus.validate_refs(["cfr_300_323", "van_duyn", "reid_v_dc"])


def test_validate_refs_raises_for_unknown():
    with pytest.raises(KeyError):
        corpus.validate_refs(["cfr_300_323", "made_up_case"])


def test_core_provisions_present():
    for pid in ["usc_1401_9", "cfr_300_320", "cfr_300_323", "cfr_300_503",
                "cfr_300_151_153", "usc_1415_sol", "endrew_f", "van_duyn",
                "reid_v_dc"]:
        assert corpus.exists(pid)


def test_regulations_and_statutes_have_urls():
    for p in corpus.CORPUS.values():
        if p.kind in (AuthorityKind.REGULATION, AuthorityKind.STATUTE):
            assert p.url.startswith("http"), f"{p.id} missing url"


def test_cases_flagged_for_verification():
    cases = corpus.by_kind(AuthorityKind.CASE)
    assert len(cases) == 3
    for c in cases:
        assert c.verify_required is True


def test_cfr_and_usc_not_flagged_for_verification():
    # Per the spec these were verified against eCFR / Cornell this session.
    for p in corpus.CORPUS.values():
        if p.kind in (AuthorityKind.REGULATION, AuthorityKind.STATUTE):
            assert p.verify_required is False
