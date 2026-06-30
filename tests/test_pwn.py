"""Tests for the Prior Written Notice 7-element checklist."""

import pytest

from due_process.models import SourceKind, SourceRef
from due_process.pwn import PWN_ELEMENTS, evaluate_pwn


def test_seven_elements_defined():
    assert len(PWN_ELEMENTS) == 7
    assert [e.number for e in PWN_ELEMENTS] == [1, 2, 3, 4, 5, 6, 7]


def test_all_present_is_compliant():
    result = evaluate_pwn({n: True for n in range(1, 8)})
    assert result.compliant is True
    assert result.missing == []
    assert len(result.present) == 7


def test_missing_elements_not_compliant():
    present = {n: True for n in range(1, 8)}
    present[6] = False
    present[7] = False
    result = evaluate_pwn(present)
    assert result.compliant is False
    missing_numbers = sorted(e.number for e in result.missing)
    assert missing_numbers == [6, 7]
    assert "(b)(6)" in result.summary()


def test_omitted_element_treated_as_absent():
    # Only elements 1-5 provided; 6 and 7 omitted entirely.
    result = evaluate_pwn({n: True for n in range(1, 6)})
    assert result.compliant is False
    assert sorted(e.number for e in result.missing) == [6, 7]


def test_string_keys_supported():
    present = {e.key: True for e in PWN_ELEMENTS}
    present["other_factors"] = False
    result = evaluate_pwn(present)
    assert result.compliant is False
    assert result.missing[0].key == "other_factors"


def test_evidence_attached():
    ref = SourceRef(kind=SourceKind.PWN, locator="p.2 ¶3",
                    description="Action described")
    result = evaluate_pwn({n: True for n in range(1, 8)},
                          evidence_by_element={1: ref})
    first = next(r for r in result.results if r.element.number == 1)
    assert first.evidence_ref is ref


def test_bad_element_key_raises():
    with pytest.raises(KeyError):
        evaluate_pwn({99: True})
    with pytest.raises(KeyError):
        evaluate_pwn({"nonsense": True})
