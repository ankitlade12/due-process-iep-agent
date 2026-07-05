"""Systemic evidence demo — from many families to one district-wide case.

    python -m due_process.examples.systemic_demo

Analyzes a district's worth of de-identified students, aggregates their
shortfalls with k-anonymity, and drafts a *systemic* state complaint that
obligates district-wide relief (34 C.F.R. 300.151(b)). Then shows a plain-language
"receipt" for one parent — translated via Qwen when a key is present — as the
low-friction, multilingual on-ramp.

The aggregation is deterministic and runs with no API calls; only the optional
translated receipt uses Qwen.
"""

from __future__ import annotations

from datetime import date

from ..analysis import analyze_commitment
from ..instruments.drafter import LetterContext, draft_systemic_complaint
from ..llm.client import default_client
from ..llm.narrative import parent_receipt
from ..scenarios import district_caseload
from ..systemic import aggregate_systemic, StudentCase, suppressed_groups

TODAY = date(2026, 6, 30)
RULE = "=" * 72


def main() -> None:
    district, students, ws, we, periods = district_caseload()
    client = default_client()

    print(RULE)
    print(f"DUE PROCESS — systemic evidence across {district}")
    print(RULE)

    cases = []
    print(f"\nPER-STUDENT (de-identified) — {len(students)} students")
    print("-" * 72)
    for sid, commitment, logs in students:
        a = analyze_commitment(commitment, logs, window_start=ws, window_end=we,
                               today=TODAY, instructional_periods=periods)
        cases.append(StudentCase(student_id=sid, district=district, analyses=[a]))
        flag = "MATERIAL" if a.materiality.is_material else "ok"
        print(f"  {sid}  speech  shortfall {a.ledger.shortfall_pct:>6.1%}  "
              f"comp {a.compensatory.estimated_minutes:>4} min   {flag}")

    findings = aggregate_systemic(cases)
    print(f"\nSYSTEMIC FINDINGS (k-anonymity >= {findings[0].k_threshold if findings else 5})")
    print("-" * 72)
    if not findings:
        print("  No pattern met the privacy + materiality thresholds.")
    for f in findings:
        print(f"  {f.service_type.value}: {f.n_students_material} of "
              f"{f.n_students_with_service} students "
              f"({f.material_student_share:.0%}) with a material failure; "
              f"aggregate unexcused shortfall {f.total_unexcused_minutes} min "
              f"({f.aggregate_shortfall_pct:.1%} of required).")

    suppressed = suppressed_groups(cases)
    if suppressed:
        print("\n  Withheld for privacy (below k-anonymity): "
              + ", ".join(f"{s.value} (n={n})" for _, s, n in suppressed))

    if findings:
        ctx = LetterContext(
            parent_name="Parent Coalition (via [PTI / advocate])",
            district_name=district,
            state_agency_name="State Education Agency, Special Education Division",
            letter_date=TODAY)
        inst = draft_systemic_complaint(findings, ctx)
        print("\n" + RULE)
        print("DRAFTED SYSTEMIC STATE COMPLAINT (de-identified)")
        print(RULE)
        print(inst.draft_text)

    # Access angle: a plain-language receipt for one parent (translated if a key
    # is present).
    lang = "es" if client.available else "en"
    receipt = parent_receipt(cases[0].analyses[0], client=client, language=lang)
    print("\n" + RULE)
    print(f"PARENT RECEIPT — 'receipts, not lawsuits'  [language: {lang}]")
    print(RULE)
    print(receipt)


if __name__ == "__main__":
    main()
