"""Tests for the evaluation harness (offline heuristic baseline)."""

from datetime import date

from due_process.analysis import analyze_commitment
from due_process.evaluation.baseline import HeuristicBaseline
from due_process.evaluation.dataset import build_dataset
from due_process.evaluation.metrics import (
    binary_metrics,
    citation_accuracy,
    mae,
)
from due_process.evaluation.run_eval import evaluate

TODAY = date(2026, 6, 30)


def _grounded_run():
    cases = build_dataset()
    labels, g_preds, b_preds = [], [], []
    comp_true, comp_pred, g_cite_ids = [], [], []
    b_total = b_valid = 0
    baseline = HeuristicBaseline()
    for case in cases:
        a = analyze_commitment(
            case.commitment, case.logs, window_start=case.window_start,
            window_end=case.window_end, today=TODAY,
            instructional_periods=case.periods)
        labels.append(case.label_material)
        g_preds.append(a.materiality.is_material)
        comp_true.append(case.label_comp_minutes)
        comp_pred.append(a.compensatory.estimated_minutes)
        if a.materiality.is_material:
            for v in a.violations:
                g_cite_ids.extend(v.legal_refs)
        b = baseline.predict(case)
        b_preds.append(b.material)
        if b.material:
            b_total += len(b.raw_citations)
            b_valid += len(b.matched_ids)
    return (labels, g_preds, b_preds, comp_true, comp_pred,
            g_cite_ids, b_total, b_valid)


def test_dataset_is_balanced():
    cases = build_dataset()
    assert len(cases) == 11
    n_material = sum(c.label_material for c in cases)
    assert 3 <= n_material <= 8  # not degenerate


def test_dataset_has_documented_cases():
    # At least some labels come from independent sources (court / guidance),
    # not just our own materiality rule.
    cases = build_dataset()
    documented = [c for c in cases if c.provenance != "synthetic"]
    assert len(documented) >= 2
    assert any("Van Duyn" in c.provenance for c in documented)


def test_grounded_system_matches_ground_truth():
    labels, g_preds, *_ = _grounded_run()
    g = binary_metrics(labels, g_preds)
    # The grounded system implements its standard consistently on the set.
    assert g.recall == 1.0
    assert g.precision == 1.0
    assert g.false_positive_rate == 0.0


def test_baseline_overflags_relative_to_grounded():
    labels, g_preds, b_preds, *_ = _grounded_run()
    g = binary_metrics(labels, g_preds)
    b = binary_metrics(labels, b_preds)
    # No-threshold baseline raises false positives the grounded system avoids.
    assert b.false_positive_rate > g.false_positive_rate


def test_grounded_citation_accuracy_beats_baseline():
    *_, g_cite_ids, b_total, b_valid = _grounded_run()
    g_acc = citation_accuracy(g_cite_ids)
    b_acc = (b_valid / b_total) if b_total else 0.0
    assert g_acc == 1.0          # every grounded cite resolves to the corpus
    assert b_acc < g_acc         # ungrounded cites do not


def test_compensatory_estimate_is_exact_on_synthetic_set():
    *_, comp_true, comp_pred, _, _, _ = _grounded_run()
    assert mae(comp_true, comp_pred) == 0.0


def test_structured_offline_report_is_reproducible():
    report = evaluate()
    assert report["mode"] == "offline-reproducible"
    assert report["dataset"]["cases"] == 11
    assert report["grounded"]["false_positive_rate"] == 0.0
    assert report["limitations"]
