"""Reproduce the spec's worked example end-to-end, with no LLM or cloud.

Run it:

    python -m due_process.examples.worked_example

It ingests the synthetic speech-therapy scenario (108 required sessions, 72
delivered, 12 excused, 24 unexcused), runs the deterministic pipeline, and prints
the detected shortfall, the materiality verdict, the compensatory estimate, the
deadline clock, and the grounded evidence — exactly the artifacts the demo
centers on.
"""

from __future__ import annotations

from datetime import date

from ..analysis import CommitmentAnalysis, analyze_commitment
from ..scenarios import worked_example_speech

# Fixed reference "today" so the printed deadline is reproducible.
TODAY = date(2026, 6, 30)

RULE = "=" * 72
THIN = "-" * 72


def _fmt_minutes(minutes: int) -> str:
    hours = minutes / 60
    return f"{minutes} min ({hours:.1f} hrs)"


def render(analysis: CommitmentAnalysis) -> str:
    led = analysis.ledger
    c = analysis.commitment
    out: list[str] = []

    out.append(RULE)
    out.append("DUE PROCESS — IEP service-delivery analysis")
    out.append(RULE)
    out.append(
        f"Service: {c.service_type.value.replace('_', ' ')} — "
        f"{c.frequency_count}x/{c.frequency_period.value}, "
        f"{c.duration_minutes} min, {c.setting.value}"
        + (f" {c.location.value}" if c.location else "")
    )
    out.append(
        f"Window:  {led.window_start.isoformat()} to {led.window_end.isoformat()}"
    )
    out.append("")

    out.append("DELIVERY LEDGER (deterministic — no LLM did this math)")
    out.append(THIN)
    out.append(f"  Required:            {led.required_sessions} sessions / "
               f"{_fmt_minutes(led.required_minutes)}")
    out.append(f"  Delivered:           {led.delivered_sessions} sessions / "
               f"{_fmt_minutes(led.delivered_minutes)}")
    out.append(f"  Excused (absences):  {led.excused_sessions} sessions / "
               f"{_fmt_minutes(led.excused_minutes)}")
    out.append(f"  Unexcused missed:    {led.unexcused_missed_sessions} sessions / "
               f"{_fmt_minutes(led.unexcused_missed_minutes)}")
    out.append(f"  Unexcused shortfall: {_fmt_minutes(led.unexcused_shortfall_minutes)} "
               f"= {led.shortfall_pct:.1%} of required")
    out.append(f"  Logs complete:       {led.logs_complete}")
    out.append("")

    out.append("MATERIALITY (configurable rule — the material-failure standard)")
    out.append(THIN)
    mat = analysis.materiality
    out.append(f"  Material failure: {mat.is_material}")
    for reason in mat.reasons:
        out.append(f"    - {reason}")
    out.append("")

    out.append("COMPENSATORY ESTIMATE")
    out.append(THIN)
    comp = analysis.compensatory
    out.append(f"  Starting position: {_fmt_minutes(comp.estimated_minutes)}")
    out.append(f"  {comp.note}")
    out.append("")

    for i, (violation, clock, bundle) in enumerate(zip(
        analysis.violations, analysis.deadlines, analysis.bundles
    )):
        out.append(f"VIOLATION: {violation.type.value} "
                   f"({_fmt_minutes(violation.shortfall_minutes)} shortfall)")
        out.append(THIN)
        out.append(f"  State-complaint deadline: {clock.sol_expiry_date.isoformat()} "
                   f"({clock.days_remaining} days left — 1-yr window, "
                   f"34 C.F.R. 300.153(c))")
        if i < len(analysis.due_process_deadlines):
            dp = analysis.due_process_deadlines[i]
            out.append(f"  Due-process deadline:     {dp.sol_expiry_date.isoformat()} "
                       f"({dp.days_remaining} days left — 2-yr, 20 U.S.C. 1415)")
        out.append(f"  Evidence cited:   {len(bundle.log_refs)} log entries, "
                   f"{len(bundle.iep_refs)} IEP ref, "
                   f"{len(bundle.legal_provisions)} legal provisions")
        out.append(f"  Grounding complete: {bundle.is_complete()}")
        out.append("")
        out.append(bundle.to_markdown())
        out.append("")

    out.append(RULE)
    out.append("Next step: draft a state complaint for parent review and approval.")
    out.append("(Drafting + human-in-the-loop approval is the next build phase.)")
    out.append(RULE)
    return "\n".join(out)


def main() -> None:
    scenario = worked_example_speech()
    analysis = analyze_commitment(
        scenario.commitment,
        scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        today=TODAY,
        instructional_periods=scenario.instructional_periods,
        discovery_date=scenario.discovery_date,
    )
    print(render(analysis))


if __name__ == "__main__":
    main()
