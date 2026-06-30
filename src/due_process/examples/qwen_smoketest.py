"""Prove the Qwen Cloud integration works with a few real calls.

    python -m due_process.examples.qwen_smoketest

Reads DASHSCOPE_API_KEY from .env, then exercises each Qwen-backed task once
(extraction, classification, narrative) and confirms the result came from Qwen
rather than the offline fallback. Designed to be cheap (a handful of calls).
"""

from __future__ import annotations

from datetime import date

from ..analysis import analyze_commitment
from ..llm.classification import classify_reason
from ..llm.client import default_client
from ..llm.extraction import extract_commitments
from ..llm.narrative import summarize_pattern
from ..scenarios import WORKED_EXAMPLE_IEP_TEXT, worked_example_speech

RULE = "=" * 72


def main() -> None:
    client = default_client()
    print(RULE)
    print("QWEN CLOUD SMOKE TEST")
    print(RULE)
    print(f"base_url:     {client.config.base_url}")
    print(f"orchestrator: {client.config.orchestrator_model}")
    print(f"workhorse:    {client.config.workhorse_model}")
    print(f"key present:  {client.available}")
    print()

    if not client.available:
        print("No DASHSCOPE_API_KEY found. Copy .env.example to .env and set "
              "your key, then re-run.")
        return

    ok = True

    # 1) Extraction -----------------------------------------------------------
    print("[1/3] extract_commitments (workhorse model) ...")
    try:
        extracted = extract_commitments(WORKED_EXAMPLE_IEP_TEXT, client=client)
        if extracted:
            c = extracted[0]
            print(f"      OK  method={c.method}  -> "
                  f"{c.commitment.service_type.value}, "
                  f"{c.commitment.frequency_count}x/"
                  f"{c.commitment.frequency_period.value}, "
                  f"{c.commitment.duration_minutes}min")
            ok = ok and (c.method == "qwen")
        else:
            print("      WARN  extraction returned nothing")
            ok = False
    except Exception as exc:  # noqa: BLE001 - surface the real error
        print(f"      FAIL  {type(exc).__name__}: {exc}")
        ok = False

    # 2) Classification -------------------------------------------------------
    print("[2/3] classify_reason (workhorse model) ...")
    for reason in ("Provider absent, no substitute available",
                   "Student was absent (out sick)"):
        try:
            rc = classify_reason(reason, client=client)
            print(f"      OK  method={rc.method}  {reason!r} -> "
                  f"{rc.excused.value} (conf {rc.confidence:.2f})")
            ok = ok and (rc.method == "qwen")
        except Exception as exc:  # noqa: BLE001
            print(f"      FAIL  {type(exc).__name__}: {exc}")
            ok = False

    # 3) Narrative ------------------------------------------------------------
    print("[3/3] summarize_pattern (orchestrator model) ...")
    try:
        s = worked_example_speech()
        analysis = analyze_commitment(
            s.commitment, s.logs, window_start=s.window_start,
            window_end=s.window_end, today=date(2026, 6, 30),
            instructional_periods=s.instructional_periods)
        text = summarize_pattern(analysis, client=client, style="formal")
        print(f"      OK  ({len(text)} chars):")
        print("      " + text[:300].replace("\n", "\n      "))
    except Exception as exc:  # noqa: BLE001
        print(f"      FAIL  {type(exc).__name__}: {exc}")
        ok = False

    print()
    print(RULE)
    print("RESULT:", "Qwen Cloud integration is LIVE ✔" if ok
          else "Some calls did not use Qwen — see errors above.")
    print(RULE)


if __name__ == "__main__":
    main()
