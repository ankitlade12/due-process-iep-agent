"""Reproducible grounded-vs-baseline evaluation.

Run the stable offline comparison used in repository documentation:

    python -m due_process.evaluation.run_eval --offline

Use ``--online`` for an explicitly live raw-Qwen baseline. Live results vary by
model/version and are deliberately not presented as the repository benchmark.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any, List, Optional

from ..analysis import analyze_commitment
from ..llm.client import LLMClient, default_client
from .baseline import HeuristicBaseline, QwenBaseline
from .dataset import build_dataset
from .metrics import binary_metrics, citation_accuracy, mae

TODAY = date(2026, 6, 30)


def evaluate(*, online: bool = False,
             client: Optional[LLMClient] = None) -> dict[str, Any]:
    """Return a structured report; offline mode is stable and network-free."""
    cases = build_dataset()
    if online:
        resolved_client = client or default_client()
        if not resolved_client.available:
            raise RuntimeError(
                "--online requires DASHSCOPE_API_KEY and the OpenAI SDK.")
        baseline = QwenBaseline(resolved_client)
    else:
        baseline = HeuristicBaseline()

    labels: List[bool] = []
    grounded_preds: List[bool] = []
    baseline_preds: List[bool] = []
    comp_true: List[int] = []
    comp_pred: List[int] = []
    grounded_citations: List[str] = []
    baseline_citation_total = 0
    baseline_citation_valid = 0
    rows = []

    for case in cases:
        analysis = analyze_commitment(
            case.commitment, case.logs,
            window_start=case.window_start, window_end=case.window_end,
            today=TODAY, instructional_periods=case.periods,
        )
        grounded_pred = analysis.materiality.is_material
        baseline_result = baseline.predict(case)
        labels.append(case.label_material)
        grounded_preds.append(grounded_pred)
        baseline_preds.append(baseline_result.material)
        comp_true.append(case.label_comp_minutes)
        comp_pred.append(
            analysis.compensatory.estimated_minutes
            if analysis.compensatory else 0)
        if grounded_pred:
            for violation in analysis.violations:
                grounded_citations.extend(violation.legal_refs)
        if baseline_result.material:
            baseline_citation_total += len(baseline_result.raw_citations)
            baseline_citation_valid += len(baseline_result.matched_ids)
        rows.append({
            "case": case.name,
            "label": case.label_material,
            "grounded": grounded_pred,
            "baseline": baseline_result.material,
            "provenance": case.provenance,
        })

    grounded = binary_metrics(labels, grounded_preds)
    base = binary_metrics(labels, baseline_preds)
    baseline_citation_accuracy = (
        baseline_citation_valid / baseline_citation_total
        if baseline_citation_total else 0.0)

    def metric_dict(value, citation_score: float) -> dict[str, float]:
        return {
            "precision": value.precision,
            "recall": value.recall,
            "f1": value.f1,
            "false_positive_rate": value.false_positive_rate,
            "accuracy": value.accuracy,
            "citation_accuracy": citation_score,
        }

    return {
        "mode": "online-qwen" if online else "offline-reproducible",
        "evaluation_date": TODAY.isoformat(),
        "dataset": {
            "cases": len(cases),
            "material": sum(labels),
            "not_material": len(cases) - sum(labels),
            "documented_or_court_derived": sum(
                1 for case in cases if case.provenance != "synthetic"),
        },
        "baseline": baseline.name,
        "grounded": metric_dict(
            grounded, citation_accuracy(grounded_citations)),
        "baseline_metrics": metric_dict(base, baseline_citation_accuracy),
        "compensatory_minutes_mae": mae(comp_true, comp_pred),
        "cases": rows,
        "limitations": [
            "Most labels are synthetic and encode the product review policy.",
            "This evaluates software consistency, not legal validity or outcomes.",
            "Online Qwen results can vary by model version and service behavior.",
        ],
    }


def _print_report(report: dict[str, Any]) -> None:
    grounded = report["grounded"]
    base = report["baseline_metrics"]
    print("=" * 72)
    print("DUE PROCESS — service-delivery review evaluation")
    print("=" * 72)
    ds = report["dataset"]
    print(f"Mode: {report['mode']}")
    print(f"Dataset: {ds['cases']} labeled cases ({ds['material']} review-signal, "
          f"{ds['not_material']} no-signal; "
          f"{ds['documented_or_court_derived']} independently documented)")
    print(f"Baseline: {report['baseline']}\n")
    print(f"{'metric':<24}{'GROUNDED':>14}{'BASELINE':>14}")
    print("-" * 72)
    for key, label in (
        ("precision", "precision"), ("recall", "recall"),
        ("f1", "F1"), ("false_positive_rate", "false-positive rate"),
        ("accuracy", "accuracy"),
        ("citation_accuracy", "citation accuracy"),
    ):
        print(f"{label:<24}{grounded[key]:>14.2f}{base[key]:>14.2f}")
    print(f"{'comp-minutes MAE':<24}"
          f"{report['compensatory_minutes_mae']:>14.1f}{'n/a':>14}\n")
    print("Per-case (label / grounded / baseline):")
    print("-" * 72)
    for row in report["cases"]:
        print(f"  {row['case']:<28} {_yn(row['label'])}   "
              f"g:{_yn(row['grounded'])}   b:{_yn(row['baseline'])}")
    print("\nLimitations:")
    for item in report["limitations"]:
        print(f"  - {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true",
                      help="stable heuristic baseline (default)")
    mode.add_argument("--online", action="store_true",
                      help="live raw-Qwen baseline; requires a key")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    args = parser.parse_args()
    report = evaluate(online=args.online)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)


def _yn(value: bool) -> str:
    return "YES" if value else "no "


if __name__ == "__main__":
    main()
