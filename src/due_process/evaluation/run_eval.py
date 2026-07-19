"""Synthetic policy-regression verification.

Run the stable, network-free engineering check:

    python -m due_process.evaluation.run_eval --offline

The scenarios encode the product's declared screening policy, so this command
verifies implementation consistency. It does not estimate real-world precision,
recall, false-positive rate, legal validity, or outcomes. ``--online`` replaces
the deliberately over-flagging contrast fixture with an exploratory raw-Qwen
contrast; those results vary and are not a benchmark.
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
from .metrics import binary_metrics, citation_validity, mae

TODAY = date(2026, 6, 30)


def evaluate(*, online: bool = False,
             client: Optional[LLMClient] = None) -> dict[str, Any]:
    """Return a policy-regression report with explicit scope limitations."""
    cases = build_dataset()
    if online:
        resolved_client = client or default_client()
        if not resolved_client.available:
            raise RuntimeError(
                "--online requires DASHSCOPE_API_KEY and the OpenAI SDK.")
        contrast = QwenBaseline(resolved_client)
    else:
        contrast = HeuristicBaseline()

    labels: List[bool] = []
    policy_predictions: List[bool] = []
    contrast_predictions: List[bool] = []
    expected_shortfalls: List[int] = []
    computed_shortfalls: List[int] = []
    grounded_citation_ids: List[str] = []
    rows = []

    for case in cases:
        analysis = analyze_commitment(
            case.commitment, case.logs,
            window_start=case.window_start, window_end=case.window_end,
            today=TODAY, instructional_periods=case.periods,
        )
        policy_prediction = analysis.materiality.is_material
        contrast_result = contrast.predict(case)
        labels.append(case.label_material)
        policy_predictions.append(policy_prediction)
        contrast_predictions.append(contrast_result.material)
        expected_shortfalls.append(case.label_comp_minutes)
        computed_shortfalls.append(
            analysis.compensatory.estimated_minutes
            if analysis.compensatory else 0)
        if policy_prediction:
            for violation in analysis.violations:
                grounded_citation_ids.extend(violation.legal_refs)
        rows.append({
            "case": case.name,
            "expected_policy_signal": case.label_material,
            "policy_pipeline_signal": policy_prediction,
            "contrast_fixture_signal": contrast_result.material,
            "provenance": case.provenance,
        })

    policy_counts = binary_metrics(labels, policy_predictions)
    contrast_counts = binary_metrics(labels, contrast_predictions)
    resolved_ids, emitted_ids = citation_validity(grounded_citation_ids)
    matching_cases = sum(
        expected == actual
        for expected, actual in zip(labels, policy_predictions))
    contrast_matches = sum(
        expected == actual
        for expected, actual in zip(labels, contrast_predictions))

    return {
        "mode": (
            "online-exploratory-contrast"
            if online else "offline-policy-regression"),
        "analysis_reference_date": TODAY.isoformat(),
        "dataset": {
            "cases": len(cases),
            "synthetic_cases": len(cases),
            "source_informed_synthetic_cases": sum(
                case.provenance.startswith("synthetic_source_informed")
                for case in cases),
            "expected_signal": sum(labels),
            "expected_no_signal": len(cases) - sum(labels),
        },
        "policy_consistency": {
            "matching_cases": matching_cases,
            "total_cases": len(cases),
            "confusion_counts": {
                "true_positive": policy_counts.tp,
                "false_positive": policy_counts.fp,
                "true_negative": policy_counts.tn,
                "false_negative": policy_counts.fn,
            },
            "interpretation": (
                "Regression check against labels generated from the declared "
                "product policy; not an accuracy estimate."),
        },
        "citation_id_integrity": {
            "resolved_ids": resolved_ids,
            "emitted_ids": emitted_ids,
            "all_ids_resolve": resolved_ids == emitted_ids,
            "interpretation": (
                "Referential integrity against the internal corpus; not legal "
                "accuracy or relevance."),
        },
        "shortfall_accounting": {
            "mae_minutes": mae(expected_shortfalls, computed_shortfalls),
            "interpretation": (
                "Arithmetic regression against expected values generated from "
                "the same synthetic facts; not external validation."),
        },
        "contrast_fixture": {
            "name": contrast.name,
            "matching_cases": contrast_matches,
            "total_cases": len(cases),
            "false_positive_count_on_policy_set": contrast_counts.fp,
            "interpretation": (
                "Deliberately limited failure-mode fixture; not a representative "
                "competitor or benchmark."),
        },
        "cases": rows,
        "limitations": [
            "All scenarios are synthetic and encode the product screening policy.",
            "The set is too small and non-representative for performance metrics.",
            "The source-informed case is not a reconstruction of the court record.",
            "Citation-ID resolution does not establish legal correctness.",
            "Independent advocate-labeled de-identified validation is not yet available.",
            "Online Qwen contrast results can vary by model and service behavior.",
        ],
    }


def _print_report(report: dict[str, Any]) -> None:
    dataset = report["dataset"]
    policy = report["policy_consistency"]
    citations = report["citation_id_integrity"]
    accounting = report["shortfall_accounting"]
    contrast = report["contrast_fixture"]

    print("=" * 72)
    print("DUE PROCESS — synthetic policy-regression verification")
    print("=" * 72)
    print(f"Mode: {report['mode']}")
    print(
        f"Dataset: {dataset['cases']} constructed synthetic cases "
        f"({dataset['source_informed_synthetic_cases']} source-informed)")
    print("Scope: engineering consistency only; not a real-world benchmark\n")
    print(
        "Policy-rule matches: "
        f"{policy['matching_cases']}/{policy['total_cases']}")
    print(
        "Internal citation IDs resolved: "
        f"{citations['resolved_ids']}/{citations['emitted_ids']}")
    print(
        "Synthetic shortfall accounting MAE: "
        f"{accounting['mae_minutes']:.1f} minutes")
    print(
        "Contrast fixture matches: "
        f"{contrast['matching_cases']}/{contrast['total_cases']} "
        f"({contrast['false_positive_count_on_policy_set']} deliberate "
        "over-flags)\n")
    print("Per-case (expected policy / implementation / contrast fixture):")
    print("-" * 72)
    for row in report["cases"]:
        print(
            f"  {row['case']:<34} {_yn(row['expected_policy_signal'])}   "
            f"p:{_yn(row['policy_pipeline_signal'])}   "
            f"c:{_yn(row['contrast_fixture_signal'])}")
    print("\nWhat these results do not measure:")
    for item in report["limitations"]:
        print(f"  - {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline", action="store_true",
        help="stable policy regression with an over-flagging contrast fixture")
    mode.add_argument(
        "--online", action="store_true",
        help="exploratory raw-Qwen contrast; requires a key; not a benchmark")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON")
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
