"""The full Track 4 (Autopilot Agent) workflow, end to end.

    python -m due_process.examples.agent_demo

Starts from raw IEP text and unclassified logs and runs the whole pipeline:
extract commitments -> classify reasons -> deterministic analysis -> draft the
right instrument -> approve -> send. It prints the audit trail, the human
checkpoints, and the drafted, approved state complaint.

Runs offline with transparent rules by default; if ``DASHSCOPE_API_KEY`` is set
it uses Qwen for extraction, classification, and the narrative.
"""

from __future__ import annotations

from datetime import datetime

from ..agent import AutoApprovePolicy, run_enforcement
from ..instruments.drafter import LetterContext
from ..llm.client import default_client
from ..scenarios import worked_example_speech

NOW = datetime(2026, 6, 30, 9, 0, 0)
RULE = "=" * 72


def main() -> None:
    scenario = worked_example_speech(classified=False)  # reasons need classifying
    client = default_client()
    mode = "Qwen (online)" if client.available else "offline rule-based"

    context = LetterContext(
        student_name="A. Doe",
        parent_name="J. Doe",
        school_name="Maple Elementary",
        district_name="Springfield SD",
        state_agency_name="State Education Agency, Special Education Division",
        letter_date=NOW.date(),
    )

    run = run_enforcement(
        scenario.logs,
        now=NOW,
        context=context,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        iep_text=scenario.iep_text,
        instructional_periods=scenario.instructional_periods,
        discovery_date=scenario.discovery_date,
        client=client,
        policy=AutoApprovePolicy(),
    )

    print(RULE)
    print(f"DUE PROCESS — Autopilot enforcement run   [LLM: {mode}]")
    print(RULE)

    print("\nAUDIT TRAIL")
    print("-" * 72)
    for line in run.audit_lines():
        print(f"  {line}")

    print("\nHUMAN CHECKPOINTS")
    print("-" * 72)
    for cp in run.checkpoints:
        mark = "resolved" if cp.resolved else f"PENDING ({cp.pending_count})"
        print(f"  [{mark}] {cp.kind}: {cp.description}")

    print("\nDRAFTED INSTRUMENTS")
    print("-" * 72)
    for inst in run.instruments:
        print(f"  - {inst.type.value}: status={inst.status.value}, "
              f"{len(inst.citations)} citations, "
              f"{len(inst.violation_ids)} violation(s)")

    # Show the headline artifact: the drafted (and approved) complaint.
    complaint = next((i for i in run.instruments
                      if i.type.value == "state_complaint"), None)
    if complaint:
        print("\n" + RULE)
        print("DRAFTED STATE COMPLAINT (for human review before sending)")
        print(RULE)
        print(complaint.draft_text)


if __name__ == "__main__":
    main()
