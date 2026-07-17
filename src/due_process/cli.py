"""Command-line interface — the real entry point (`due-process`).

Ties the pieces into commands a parent or advocate could actually run:

    due-process worked-example
    due-process analyze --logs logs.csv --service speech --freq 3 --duration 30 \
        --periods 36 --state NY --student-name "Jordan Rivera" --draft --packet out.txt
    due-process pwn --file notice.txt
    due-process vision --image iep.png --student-name "Jordan Rivera"
    due-process version

Uses Qwen when DASHSCOPE_API_KEY is set, else the offline rule-based paths.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import List, Optional

from . import __version__
from .analysis import analyze_commitment
from .filing import export_evidence_packet, filing_instructions
from .ingest import load_logs_csv
from .instruments.drafter import LetterContext, draft_pwn_request, draft_state_complaint
from .llm.classification import classify_logs
from .llm.client import default_client
from .models import (
    DeliverySetting,
    FrequencyPeriod,
    ServiceCommitment,
    ServiceType,
)
from .privacy import Redactor
from .pwn import evaluate_pwn

_SERVICE_ALIASES = {
    "speech": ServiceType.SPEECH_LANGUAGE,
    "speech_language": ServiceType.SPEECH_LANGUAGE,
    "slp": ServiceType.SPEECH_LANGUAGE,
    "ot": ServiceType.OCCUPATIONAL_THERAPY,
    "occupational_therapy": ServiceType.OCCUPATIONAL_THERAPY,
    "pt": ServiceType.PHYSICAL_THERAPY,
    "physical_therapy": ServiceType.PHYSICAL_THERAPY,
    "counseling": ServiceType.COUNSELING,
    "behavioral_support": ServiceType.BEHAVIORAL_SUPPORT,
    "specialized_instruction": ServiceType.SPECIALIZED_INSTRUCTION,
}

RULE = "=" * 72


def _fmt_minutes(m: int) -> str:
    return f"{m} min ({m / 60:.1f} hrs)"


def cmd_worked_example(_args) -> int:
    from .examples.worked_example import main as wmain
    wmain()
    return 0


def cmd_version(_args) -> int:
    print(f"due-process {__version__}")
    return 0


def cmd_analyze(args) -> int:
    service = _SERVICE_ALIASES.get(args.service.lower())
    if service is None:
        print(f"Unknown --service {args.service!r}. Options: "
              f"{sorted(set(_SERVICE_ALIASES))}", file=sys.stderr)
        return 2

    client = default_client()
    redactor = (Redactor.for_case(student_name=args.student_name)
                if args.student_name else None)
    today = date.fromisoformat(args.today) if args.today else date.today()

    commitment = ServiceCommitment(
        id="svc-1", service_type=service, frequency_count=args.freq,
        frequency_period=FrequencyPeriod.WEEK, duration_minutes=args.duration,
        setting=DeliverySetting.INDIVIDUAL)

    try:
        logs = load_logs_csv(args.logs, "svc-1", scheduled_minutes=args.duration)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not read logs: {exc}", file=sys.stderr)
        return 2
    if not logs:
        print("No log rows parsed.", file=sys.stderr)
        return 2

    # Classify reasons (CSV reason column -> excused/unexcused), then analyze.
    classify_logs(logs, client=client, redactor=redactor)
    window_start = min(l.date for l in logs)
    window_end = max(l.date for l in logs)
    commitment.effective_start = window_start
    analysis = analyze_commitment(
        commitment, logs, window_start=window_start, window_end=window_end,
        today=today, instructional_periods=args.periods, state=args.state)

    led = analysis.ledger
    print(RULE)
    print(f"DUE PROCESS — {service.value} analysis  "
          f"[LLM: {'qwen' if client.available else 'offline'}]")
    print(RULE)
    print(f"  Required:   {led.required_sessions} sessions / "
          f"{_fmt_minutes(led.required_minutes)}")
    print(f"  Delivered:  {led.delivered_sessions} / "
          f"{_fmt_minutes(led.delivered_minutes)}")
    print(f"  Excused:    {led.excused_sessions} / "
          f"{_fmt_minutes(led.excused_minutes)}")
    print(f"  Unexcused shortfall: {_fmt_minutes(led.unexcused_shortfall_minutes)} "
          f"= {led.shortfall_pct:.1%}")
    print(f"  Logs complete: {led.logs_complete}")
    print(f"  Material failure: {analysis.materiality.is_material}")
    if analysis.compensatory:
        print(f"  Compensatory estimate: "
              f"{_fmt_minutes(analysis.compensatory.estimated_minutes)} (equitable)")
    if analysis.deadlines:
        sc = analysis.deadlines[0]
        print(f"  State-complaint deadline: {sc.sol_expiry_date.isoformat()} "
              f"({sc.days_remaining} days — 1-yr, 34 CFR 300.153(c))")
    if analysis.due_process_deadlines:
        dp = analysis.due_process_deadlines[0]
        print(f"  Due-process deadline:     {dp.sol_expiry_date.isoformat()} "
              f"({dp.days_remaining} days — 2-yr, 20 USC 1415)")

    info = filing_instructions(args.state)
    print(f"\n  Where to file: {info.agency_name}")
    if info.url:
        print(f"    {info.url}")

    if args.draft or args.packet:
        context = LetterContext(
            student_name=args.student_name or "[Student]",
            state=args.state, letter_date=today)
        inst = draft_state_complaint([analysis], context, client=client)
        if args.draft:
            print("\n" + RULE)
            print("DRAFTED STATE COMPLAINT (review before sending)")
            print(RULE)
            print(inst.draft_text)
        if args.packet:
            export_evidence_packet(inst, [analysis], state=args.state,
                                   filename=args.packet)
            print(f"\nWrote evidence packet to {args.packet}")
    return 0


def cmd_pwn(args) -> int:
    from .llm.pwn_detect import detect_pwn_elements

    try:
        text = open(args.file, encoding="utf-8").read()
    except OSError as exc:
        print(f"Could not read PWN file: {exc}", file=sys.stderr)
        return 2

    client = default_client()
    redactor = (Redactor.for_case(student_name=args.student_name)
                if args.student_name else None)
    detection = detect_pwn_elements(text, client=client, redactor=redactor)
    result = evaluate_pwn(detection.present_by_element)

    print(RULE)
    print(f"PWN COMPLIANCE CHECK — 34 C.F.R. 300.503(b)  "
          f"[detector: {detection.method}]")
    print(RULE)
    print(f"  {result.summary()}")
    for r in result.results:
        mark = "ok " if r.present else "MISSING"
        print(f"   [{mark}] (b)({r.element.number}) {r.element.description[:64]}")

    if not result.compliant and args.draft_request:
        missing = [f"(b)({e.number}) {e.description}" for e in result.missing]
        inst = draft_pwn_request(
            LetterContext(student_name=args.student_name or "[Student]",
                          letter_date=date.today()),
            missing_elements=missing, client=client)
        print("\n" + RULE)
        print("DRAFTED PWN REQUEST")
        print(RULE)
        print(inst.draft_text)
    return 0


def cmd_vision(args) -> int:
    from .ingest import read_iep_image
    from .llm.extraction import extract_commitments

    client = default_client()
    if not client.available:
        print("Vision needs DASHSCOPE_API_KEY.", file=sys.stderr)
        return 2
    redactor = (Redactor.for_case(student_name=args.student_name)
                if args.student_name else None)
    text = read_iep_image(
        args.image, client, redactor=redactor,
        image_is_redacted_or_synthetic=args.redacted_or_synthetic,
    )
    print("--- TRANSCRIPTION ---")
    print(text)
    print("\n--- PARSED SERVICES ---")
    for e in extract_commitments(text):
        c = e.commitment
        print(f"  {c.service_type.value}: {c.frequency_count}x/"
              f"{c.frequency_period.value}, {c.duration_minutes}min")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="due-process",
                                description="IEP enforcement agent.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("worked-example",
                   help="run the spec's worked example").set_defaults(
        func=cmd_worked_example)
    sub.add_parser("version", help="print version").set_defaults(func=cmd_version)

    a = sub.add_parser("analyze", help="analyze service logs against a commitment")
    a.add_argument("--logs", required=True, help="CSV/TSV log file or text")
    a.add_argument("--service", required=True, help="speech|ot|pt|...")
    a.add_argument("--freq", type=int, default=1, help="sessions per week")
    a.add_argument("--duration", type=int, default=30, help="minutes per session")
    a.add_argument("--periods", type=int, default=36, help="instructional weeks")
    a.add_argument("--state", default="", help="two-letter state code")
    a.add_argument("--student-name", default="", help="for PII redaction")
    a.add_argument("--today", default="", help="reference date YYYY-MM-DD")
    a.add_argument("--draft", action="store_true", help="draft a state complaint")
    a.add_argument("--packet", default="", help="write evidence packet to file")
    a.set_defaults(func=cmd_analyze)

    w = sub.add_parser("pwn", help="check a Prior Written Notice for the 7 elements")
    w.add_argument("--file", required=True, help="PWN text file")
    w.add_argument("--student-name", default="", help="for PII redaction")
    w.add_argument("--draft-request", action="store_true",
                   help="draft a PWN request if non-compliant")
    w.set_defaults(func=cmd_pwn)

    v = sub.add_parser("vision", help="read a scanned IEP image via Qwen vision")
    v.add_argument("--image", required=True, help="PNG/JPG of an IEP page")
    v.add_argument("--student-name", default="", help="redact PII in the output")
    v.add_argument(
        "--redacted-or-synthetic", action="store_true", required=True,
        help="confirm the image contains no real unredacted student PII",
    )
    v.set_defaults(func=cmd_vision)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
