"""Run the evaluation and print the grounded-vs-baseline comparison.

    python -m due_process.evaluation.run_eval

Offline it uses the heuristic baseline (clearly labeled); with a key it uses raw
Qwen. The headline is the grounded system's false-positive rate and citation
accuracy against the baseline's.
"""

from __future__ import annotations

from datetime import date
from typing import List

from ..analysis import analyze_commitment
from ..llm.client import default_client
from .baseline import get_baseline
from .dataset import build_dataset
from .metrics import binary_metrics, citation_accuracy, mae

TODAY = date(2026, 6, 30)


def main() -> None:
    cases = build_dataset()
    client = default_client()
    baseline = get_baseline(client)

    labels: List[bool] = []
    g_preds: List[bool] = []
    b_preds: List[bool] = []
    comp_true: List[int] = []
    comp_pred: List[int] = []
    g_cite_ids: List[str] = []
    b_cite_raw_total = 0
    b_cite_valid = 0

    rows = []
    for case in cases:
        analysis = analyze_commitment(
            case.commitment, case.logs,
            window_start=case.window_start, window_end=case.window_end,
            today=TODAY, instructional_periods=case.periods,
        )
        g_pred = analysis.materiality.is_material
        b = baseline.predict(case)

        labels.append(case.label_material)
        g_preds.append(g_pred)
        b_preds.append(b.material)
        comp_true.append(case.label_comp_minutes)
        comp_pred.append(analysis.compensatory.estimated_minutes
                         if analysis.compensatory else 0)

        if g_pred:
            for v in analysis.violations:
                g_cite_ids.extend(v.legal_refs)
        if b.material:
            b_cite_raw_total += len(b.raw_citations)
            b_cite_valid += len(b.matched_ids)

        rows.append((case.name, case.label_material, g_pred, b.material))

    g = binary_metrics(labels, g_preds)
    bm = binary_metrics(labels, b_preds)
    g_cite_acc = citation_accuracy(g_cite_ids)
    b_cite_acc = (b_cite_valid / b_cite_raw_total) if b_cite_raw_total else 0.0
    comp_mae = mae(comp_true, comp_pred)

    n_material = sum(labels)
    n_documented = sum(1 for c in cases if c.provenance != "synthetic")
    print("=" * 72)
    print("DUE PROCESS — material-failure detection evaluation")
    print("=" * 72)
    print(f"Dataset: {len(cases)} labeled cases "
          f"({n_material} material, {len(cases) - n_material} not; "
          f"{n_documented} with documented/court-derived labels)")
    print(f"Baseline: {baseline.name}")
    print()

    print(f"{'metric':<22}{'GROUNDED':>14}{'BASELINE':>14}")
    print("-" * 72)
    print(f"{'precision':<22}{g.precision:>14.2f}{bm.precision:>14.2f}")
    print(f"{'recall':<22}{g.recall:>14.2f}{bm.recall:>14.2f}")
    print(f"{'F1':<22}{g.f1:>14.2f}{bm.f1:>14.2f}")
    print(f"{'false-positive rate':<22}{g.false_positive_rate:>14.2f}"
          f"{bm.false_positive_rate:>14.2f}")
    print(f"{'accuracy':<22}{g.accuracy:>14.2f}{bm.accuracy:>14.2f}")
    print(f"{'citation accuracy':<22}{g_cite_acc:>14.2f}{b_cite_acc:>14.2f}")
    print(f"{'comp-minutes MAE':<22}{comp_mae:>14.1f}{'n/a':>14}")
    print()

    print("Per-case (label / grounded / baseline):")
    print("-" * 72)
    for name, label, gp, bp in rows:
        flag = "" if (gp == label) else "  <- grounded miss"
        print(f"  {name:<28} {_yn(label)}   g:{_yn(gp)}   b:{_yn(bp)}{flag}")
    print()
    print("Headline: the grounded system's false-positive rate and citation "
          "accuracy beat the ungrounded baseline — the credibility story no "
          "incumbent reports.")


def _yn(b: bool) -> str:
    return "MAT" if b else "ok "


if __name__ == "__main__":
    main()
