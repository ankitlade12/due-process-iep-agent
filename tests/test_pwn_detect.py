"""Tests for the PWN element detector (offline keyword path) + evaluation."""

from due_process.llm.pwn_detect import detect_pwn_elements
from due_process.pwn import evaluate_pwn

_COMPLIANT = """PRIOR WRITTEN NOTICE
The district proposes to reduce speech services from 3x to 2x weekly.
This is because recent progress data show the student met the articulation goal.
This decision is based on the speech-language evaluation and progress reports.
You have protection under the procedural safeguards; a copy of your rights is
available on request. If you need assistance in understanding these provisions,
contact the Parent Training and Information center. The team considered other
options, including maintaining 3x weekly, but rejected that as unnecessary.
Other relevant factors: the student's schedule was also considered.
"""

_DEFICIENT = """The district proposes to change placement. This is because of new
evaluation data, based on the assessment and reports. You have procedural
safeguards and may request a copy. Contact the parent center for assistance.
"""


def test_detects_all_seven_in_compliant_pwn():
    detection = detect_pwn_elements(_COMPLIANT)
    result = evaluate_pwn(detection.present_by_element)
    assert result.compliant is True
    assert result.missing == []


def test_flags_missing_elements():
    detection = detect_pwn_elements(_DEFICIENT)
    result = evaluate_pwn(detection.present_by_element)
    assert result.compliant is False
    missing = sorted(e.number for e in result.missing)
    # Missing "other options considered" (6) and "other factors" (7).
    assert 6 in missing and 7 in missing


def test_method_is_rule_based_offline():
    assert detect_pwn_elements(_COMPLIANT).method == "rule_based"
