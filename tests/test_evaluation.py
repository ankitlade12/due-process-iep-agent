"""Tests for synthetic policy-regression verification."""

import json
from datetime import date

from due_process.analysis import analyze_commitment
from due_process.evaluation.baseline import HeuristicBaseline
from due_process.evaluation.dataset import build_dataset
from due_process.evaluation.metrics import citation_id_resolution_rate, mae
from due_process.evaluation.run_eval import evaluate

TODAY = date(2026, 6, 30)


def _policy_regression_run():
    cases = build_dataset()
    labels, policy_predictions, contrast_predictions = [], [], []
    expected_shortfalls, computed_shortfalls, citation_ids = [], [], []
    contrast = HeuristicBaseline()
    for case in cases:
        analysis = analyze_commitment(
            case.commitment, case.logs, window_start=case.window_start,
            window_end=case.window_end, today=TODAY,
            instructional_periods=case.periods)
        labels.append(case.label_material)
        policy_predictions.append(analysis.materiality.is_material)
        expected_shortfalls.append(case.label_comp_minutes)
        computed_shortfalls.append(analysis.compensatory.estimated_minutes)
        if analysis.materiality.is_material:
            for violation in analysis.violations:
                citation_ids.extend(violation.legal_refs)
        contrast_predictions.append(contrast.predict(case).material)
    return (
        labels,
        policy_predictions,
        contrast_predictions,
        expected_shortfalls,
        computed_shortfalls,
        citation_ids,
    )


def test_dataset_is_small_balanced_and_entirely_synthetic():
    cases = build_dataset()
    assert len(cases) == 11
    n_signal = sum(case.label_material for case in cases)
    assert 3 <= n_signal <= 8
    assert all(case.provenance.startswith("synthetic") for case in cases)


def test_dataset_has_one_source_informed_but_not_court_labeled_case():
    cases = build_dataset()
    source_informed = [
        case for case in cases
        if case.provenance.startswith("synthetic_source_informed")]
    assert len(source_informed) == 1
    assert "Van Duyn" in source_informed[0].provenance
    assert "not a reconstruction" in source_informed[0].notes


def test_policy_implementation_matches_constructed_expectations():
    labels, policy_predictions, *_ = _policy_regression_run()
    assert policy_predictions == labels


def test_deliberately_overflagging_fixture_exercises_known_failure():
    labels, policy_predictions, contrast_predictions, *_ = (
        _policy_regression_run())
    assert contrast_predictions != policy_predictions
    assert any(
        contrast and not expected
        for expected, contrast in zip(labels, contrast_predictions))


def test_internal_citation_ids_resolve_to_controlled_corpus():
    *_, citation_ids = _policy_regression_run()
    assert citation_ids
    assert citation_id_resolution_rate(citation_ids) == 1.0


def test_shortfall_accounting_matches_generated_synthetic_values():
    *_, expected_shortfalls, computed_shortfalls, _ = _policy_regression_run()
    assert mae(expected_shortfalls, computed_shortfalls) == 0.0


def test_structured_report_refuses_to_present_accuracy_claims():
    report = evaluate()
    serialized = json.dumps(report)
    assert report["mode"] == "offline-policy-regression"
    assert report["dataset"]["cases"] == 11
    assert report["dataset"]["synthetic_cases"] == 11
    assert report["policy_consistency"]["matching_cases"] == 11
    assert report["citation_id_integrity"]["all_ids_resolve"] is True
    assert "precision" not in serialized
    assert "recall" not in serialized
    assert "citation_accuracy" not in serialized
    assert report["limitations"]
