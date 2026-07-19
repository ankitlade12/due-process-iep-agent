"""Streamlit advocate case desk for the Due Process demo.

Run:
    streamlit run src/due_process/examples/case_desk.py

The UI is a presentation layer over the real backend workflow: Qwen extraction
and classification when configured, deterministic ledger analysis, evidence
grounding, draft generation, human checkpoints, and systemic aggregation.
"""

from __future__ import annotations

import html
import queue
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from due_process.agent import (
    ApprovalPolicy,
    PreparedEnforcementInputs,
    prepare_enforcement_inputs,
    run_enforcement,
)
from due_process.analysis import analyze_commitment
from due_process.examples.redacted_case import (
    REDACTED_CASE_DISTRICT,
    REDACTED_CASE_END,
    REDACTED_CASE_IEP_TEXT,
    REDACTED_CASE_LOG_CSV,
    REDACTED_CASE_PERIODS,
    REDACTED_CASE_PROVIDER_NOTE,
    REDACTED_CASE_SCHOOL,
    REDACTED_CASE_START,
    REDACTED_CASE_STUDENT,
)
from due_process.filing import export_evidence_packet
from due_process.ingest import load_logs_csv
from due_process.instruments.drafter import LetterContext, draft_systemic_complaint
from due_process.llm.client import default_client
from due_process.models import (
    DeliverySetting,
    ExcusedClass,
    FrequencyPeriod,
    LogStatus,
    ServiceLocation,
    ServiceType,
)
from due_process.scenarios import district_caseload, worked_example_speech
from due_process.systemic import StudentCase, aggregate_systemic

TODAY = date.today()


class DraftOnlyDemoPolicy(ApprovalPolicy):
    """Confirm inputs and draft a remedy, but never approve external action."""

    name = "draft-only demo"

    def confirm_commitments(self, extracted):
        return True


class ConfirmedReviewPolicy(DraftOnlyDemoPolicy):
    """Human decisions captured by the case-desk review form."""

    name = "interactive human review"

    def __init__(self, ambiguity_decisions: dict[str, ExcusedClass]):
        self.ambiguity_decisions = ambiguity_decisions

    def resolve_ambiguous(self, items):
        return {
            item.id: self.ambiguity_decisions[item.id]
            for item in items if item.id in self.ambiguity_decisions
        }


@dataclass
class PreparedCaseReview:
    """In-memory review state kept server-side between Streamlit reruns."""

    iep_text: str
    logs: list
    window_start: date
    window_end: date
    instructional_periods: int
    context: LetterContext
    state: str
    include_systemic_demo: bool
    use_qwen: bool
    client: Any
    prepared_inputs: PreparedEnforcementInputs
    trace_start: int

    @property
    def commitment(self):
        return self.prepared_inputs.extracted[0].commitment

    def ambiguity_rows(self) -> list[dict[str, Any]]:
        rows = []
        for log in self.prepared_inputs.classification.review_items:
            result = self.prepared_inputs.classification.classifications[log.id]
            rows.append({
                "id": log.id,
                "date": log.date.isoformat(),
                "reason": log.missed_reason_text or "No reason recorded",
                "rationale": result.rationale,
                "method": result.method,
                "confidence": result.confidence,
            })
        return rows


def _minutes(value: int) -> str:
    return f"{value:,} min"


def _pct(value) -> str:
    return f"{value:.1%}"


def _method_counts(items: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items.values():
        counts[item.method] = counts.get(item.method, 0) + 1
    return counts


def _systemic_payload() -> dict[str, Any]:
    """Build the synthetic, privacy-gated cohort used only in the demo tab."""
    district, students, ws, we, periods = district_caseload()
    district_cases: list[StudentCase] = []
    for sid, commitment, logs in students:
        district_analysis = analyze_commitment(
            commitment, logs, window_start=ws, window_end=we, today=TODAY,
            instructional_periods=periods,
        )
        district_cases.append(StudentCase(
            student_id=sid, district=district, analyses=[district_analysis]))
    finding = aggregate_systemic(district_cases)[0]
    systemic_draft = draft_systemic_complaint(
        [finding],
        LetterContext(parent_name="Parent Coalition", district_name=district,
                      state_agency_name="State Education Agency",
                      letter_date=TODAY),
    )
    return {
        "district": finding.district,
        "service": finding.service_type.value.replace("_", " ").title(),
        "students_with_service": finding.n_students_with_service,
        "students_material": finding.n_students_material,
        "share_material": _pct(finding.material_student_share),
        "aggregate_gap": finding.total_unexcused_minutes,
        "aggregate_gap_label": _minutes(finding.total_unexcused_minutes),
        "k_threshold": finding.k_threshold,
        "draft_preview": systemic_draft.draft_text,
        "synthetic": True,
    }


def prepare_case_review(
    *,
    iep_text: str,
    logs: list,
    window_start: date,
    window_end: date,
    instructional_periods: int,
    context: LetterContext,
    use_qwen: bool = True,
    state: str = "",
    include_systemic_demo: bool = False,
) -> PreparedCaseReview:
    """Run Qwen/rules only, then stop for a real human review checkpoint."""
    if not iep_text.strip():
        raise ValueError("IEP service text is required.")
    if not logs:
        raise ValueError("At least one service-log row is required.")
    client = default_client() if use_qwen else None
    trace_start = len(client.traces) if client is not None else 0
    prepared = prepare_enforcement_inputs(
        logs,
        iep_text=iep_text,
        context=context,
        client=client,
        source_uri=(
            "synthetic://worked-example/iep-services"
            if include_systemic_demo
            else "uploaded://iep-services-text"
        ),
    )
    if not prepared.extracted:
        raise ValueError(
            "No service commitment was extracted. Include a service, frequency, "
            "and duration in the IEP text.")
    if len(prepared.extracted) != 1:
        raise ValueError(
            "This review accepts one service commitment per log upload. Split "
            "multi-service records into one review per service.")
    return PreparedCaseReview(
        iep_text=iep_text,
        logs=logs,
        window_start=window_start,
        window_end=window_end,
        instructional_periods=instructional_periods,
        context=context,
        state=state,
        include_systemic_demo=include_systemic_demo,
        use_qwen=use_qwen,
        client=client,
        prepared_inputs=prepared,
        trace_start=trace_start,
    )


def finalize_case_review(
    review: PreparedCaseReview,
    *,
    service_type: str,
    frequency_count: int,
    frequency_period: str,
    duration_minutes: int,
    setting: str,
    location: str | None = None,
    group_size_max: int | None = None,
    ambiguity_decisions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply explicit human decisions and only then run deterministic analysis."""
    if not 1 <= int(frequency_count) <= 20:
        raise ValueError("Frequency must be between 1 and 20 sessions per period.")
    if not 1 <= int(duration_minutes) <= 480:
        raise ValueError("Duration must be between 1 and 480 minutes.")
    decisions = {
        log_id: ExcusedClass(value)
        for log_id, value in (ambiguity_decisions or {}).items()
        if value in (ExcusedClass.EXCUSED.value, ExcusedClass.UNEXCUSED.value)
    }
    required_ids = {
        row["id"] for row in review.ambiguity_rows()
    }
    missing = required_ids - set(decisions)
    if missing:
        raise ValueError(
            f"Resolve every ambiguous reason before analysis ({len(missing)} pending).")

    original = review.commitment
    confirmed = replace(
        original,
        service_type=ServiceType(service_type),
        frequency_count=int(frequency_count),
        frequency_period=FrequencyPeriod(frequency_period),
        duration_minutes=int(duration_minutes),
        setting=DeliverySetting(setting),
        location=(
            original.location if location is None
            else ServiceLocation(location) if location else None),
        group_size_max=(
            original.group_size_max if group_size_max is None
            else int(group_size_max) if group_size_max != 0 else None),
    )
    review.prepared_inputs.extracted[0].commitment = confirmed
    return build_case_payload(
        iep_text=review.iep_text,
        logs=review.logs,
        window_start=review.window_start,
        window_end=review.window_end,
        instructional_periods=review.instructional_periods,
        context=review.context,
        use_qwen=review.use_qwen,
        state=review.state,
        include_systemic_demo=review.include_systemic_demo,
        client=review.client,
        prepared_inputs=review.prepared_inputs,
        policy=ConfirmedReviewPolicy(decisions),
        trace_start=review.trace_start,
    )


def build_case_payload(
    *,
    iep_text: str,
    logs: list,
    window_start: date,
    window_end: date,
    instructional_periods: int,
    context: LetterContext,
    use_qwen: bool = True,
    state: str = "",
    include_systemic_demo: bool = False,
    client: Any = None,
    prepared_inputs: PreparedEnforcementInputs | None = None,
    policy: ApprovalPolicy | None = None,
    trace_start: int | None = None,
) -> dict[str, Any]:
    """Run one real input bundle and return the UI's JSON-safe view model."""
    started = time.perf_counter()
    client = client or (default_client() if use_qwen else None)
    if trace_start is None:
        trace_start = len(client.traces) if client is not None else 0

    run = run_enforcement(
        logs,
        now=datetime.now(),
        context=context,
        window_start=window_start,
        window_end=window_end,
        iep_text=iep_text,
        instructional_periods=instructional_periods,
        discovery_date=window_end,
        state=state,
        client=client,
        policy=policy or DraftOnlyDemoPolicy(),
        prepared_inputs=prepared_inputs,
        require_all_ambiguities_resolved=prepared_inputs is not None,
    )
    if not run.analyses:
        raise ValueError(
            "No reviewable service commitment was extracted. Include a service, "
            "frequency, and duration in the IEP text."
        )
    analysis = run.analyses[0]
    ledger = analysis.ledger
    deadline = analysis.deadlines[0] if analysis.deadlines else None
    due_process_deadline = (
        analysis.due_process_deadlines[0]
        if analysis.due_process_deadlines else None)
    draft = run.instruments[0] if run.instruments else None
    bundle = analysis.bundles[0] if analysis.bundles else None

    comp_minutes = analysis.compensatory.estimated_minutes if analysis.compensatory else 0
    class_counts = _method_counts(run.classification.classifications if run.classification else {})
    extracted_method = run.extracted[0].method if run.extracted else "none"
    extraction_fallback = (run.extracted[0].fallback_reason
                           if run.extracted else "")
    classification_fallbacks = sorted({
        item.fallback_reason
        for item in (run.classification.classifications.values()
                     if run.classification else [])
        if item.fallback_reason
    })
    missed_count = sum(1 for log in logs if log.status == LogStatus.MISSED)
    duration_ms = int((time.perf_counter() - started) * 1000)
    traces = client.traces[trace_start:] if client is not None else []
    trace_rows = [
        {
            "model": trace.model,
            "operation": trace.operation,
            "succeeded": trace.succeeded,
            "duration_ms": trace.duration_ms,
            "request_id": trace.request_id,
            "error_type": trace.error_type,
        }
        for trace in traces
    ]
    qwen_outputs = (
        extracted_method == "qwen" or class_counts.get("qwen", 0) > 0)
    qwen_succeeded = any(trace.succeeded for trace in traces)
    if qwen_outputs and qwen_succeeded:
        mode = "qwen-online"
    elif use_qwen and traces:
        mode = "mixed-fallback"
    else:
        mode = "offline-fallback"

    claims: list[dict[str, Any]] = []
    if bundle is not None:
        claims.append({
            "title": "Implementation review signal",
            "finding": (
                f"{_minutes(ledger.unexcused_shortfall_minutes)} unexcused "
                f"shortfall ({_pct(ledger.shortfall_pct)})."),
            "iep": bundle.iep_refs[0].cite() if bundle.iep_refs else "services line",
            "logs": [ref.cite() for ref in bundle.log_refs[:10]],
            "law": [p.short_label for p in bundle.legal_provisions],
        })
    else:
        claims.append({
            "title": "No actionable violation generated",
            "finding": analysis.materiality.reasons[0],
            "iep": (analysis.commitment.source_ref.cite()
                    if analysis.commitment.source_ref else "services line"),
            "logs": [f"{len(logs)} service-log rows reviewed"],
            "law": [],
        })
    if draft is not None:
        claims.append({
            "title": "Draft remedy gated by a human",
            "finding": f"{_minutes(comp_minutes)} compensatory estimate; draft ready.",
            "iep": "Human approval required before any external action.",
            "logs": ([f"State complaint event deadline: {deadline.sol_expiry_date.isoformat()}"]
                     if deadline else ["Complete service logs requested first"]),
            "law": draft.citations,
        })

    packet_text = (
        export_evidence_packet(draft, run.analyses, state=state)
        if draft is not None else "")
    material_label = "review signal found" if analysis.materiality.is_material else "no review signal"

    return {
        "run_id": f"demo-{int(time.time())}",
        "status": "needs_human_approval" if run.needs_human else "complete",
        "mode": mode,
        "duration_ms": duration_ms,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "case": {
            "student": context.student_name,
            "school": context.school_name,
            "district": context.district_name,
            "service": analysis.commitment.service_type.value.replace("_", " ").title(),
            "window": f"{ledger.window_start.isoformat()} to {ledger.window_end.isoformat()}",
            "iep_text": iep_text.strip(),
            "logs": len(logs),
            "missed_logs": missed_count,
        },
        "agent_steps": [
            {
                "label": "Read IEP",
                "owner": "Qwen" if extracted_method == "qwen" else "rules",
                "detail": (f"{len(run.extracted)} commitment extracted by "
                           f"{extracted_method}."
                           + (f" Fallback: {extraction_fallback}."
                              if extraction_fallback else "")),
            },
            {
                "label": "Classify logs",
                "owner": "Qwen" if class_counts.get("qwen", 0) else "rules",
                "detail": (f"{len(run.classification.classifications)} missed/short "
                           f"reasons classified: {class_counts}."),
            },
            {
                "label": "Run ledger",
                "owner": "deterministic",
                "detail": f"{ledger.required_sessions} required sessions reconciled against {len(logs)} logs.",
            },
            {
                "label": "Apply materiality",
                "owner": "deterministic",
                "detail": analysis.materiality.reasons[0],
            },
            {
                "label": "Ground claims",
                "owner": "deterministic",
                "detail": (f"{len(bundle.log_refs)} log refs, {len(bundle.iep_refs)} "
                           f"IEP refs, {len(bundle.legal_provisions)} legal refs."
                           if bundle else "No allegation was published."),
            },
            {
                "label": "Draft remedy",
                "owner": "agent",
                "detail": (f"{draft.type.value.replace('_', ' ').title()} drafted "
                           "and held for human approval."
                           if draft else "No outbound document was needed."),
            },
        ],
        "ledger": {
            "required_sessions": ledger.required_sessions,
            "required_minutes": ledger.required_minutes,
            "delivered_sessions": ledger.delivered_sessions,
            "delivered_minutes": ledger.delivered_minutes,
            "excused_sessions": ledger.excused_sessions,
            "unexcused_sessions": ledger.unexcused_missed_sessions,
            "unexcused_minutes": ledger.unexcused_shortfall_minutes,
            "shortfall_pct": _pct(ledger.shortfall_pct),
            "logs_complete": ledger.logs_complete,
            "comp_minutes": comp_minutes,
            "comp_hours": f"{comp_minutes / 60:.1f}",
        },
        "qwen": {
            "configured": bool(client and client.available),
            "used_for_output": qwen_outputs,
            "extraction_method": extracted_method,
            "extraction_fallback": extraction_fallback,
            "classification_methods": class_counts,
            "classification_fallbacks": classification_fallbacks,
            "orchestrator_model": client.config.orchestrator_model if client else "none",
            "workhorse_model": client.config.workhorse_model if client else "none",
            "traces": trace_rows,
        },
        "deterministic": {
            "material": analysis.materiality.is_material,
            "materiality_reason": analysis.materiality.reasons[0],
            "state_deadline": deadline.sol_expiry_date.isoformat() if deadline else "n/a",
            "state_days_remaining": deadline.days_remaining if deadline else None,
            "due_process_deadline": (due_process_deadline.sol_expiry_date.isoformat()
                                     if due_process_deadline else "n/a"),
            "due_process_days_remaining": (due_process_deadline.days_remaining
                                            if due_process_deadline else None),
            "label": material_label,
        },
        "claims": claims,
        "checkpoints": [
            {
                "kind": cp.kind,
                "description": cp.description,
                "resolved": cp.resolved,
                "pending": cp.pending_count,
            }
            for cp in run.checkpoints
        ],
        "systemic": _systemic_payload() if include_systemic_demo else None,
        "audit": run.audit_lines(),
        "draft": {
            "type": draft.type.value if draft else "none",
            "status": draft.status.value if draft else "not_needed",
            "citations": draft.citations if draft else [],
            "text": draft.draft_text if draft else "No draft was generated.",
            "packet": packet_text,
        },
    }


def build_run_payload(*, use_qwen: bool = True) -> dict[str, Any]:
    """Execute the polished synthetic demo through the same real input path."""
    scenario = worked_example_speech(classified=False)
    return build_case_payload(
        iep_text=scenario.iep_text,
        logs=scenario.logs,
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        instructional_periods=scenario.instructional_periods,
        context=LetterContext(
            student_name="A. Doe", parent_name="J. Doe",
            school_name="Maple Elementary", district_name="Springfield SD",
            state_agency_name="State Education Agency", letter_date=TODAY),
        use_qwen=use_qwen,
        include_systemic_demo=True,
    )


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        :root {
            --dp-ink: #16252d;
            --dp-muted: #61727d;
            --dp-teal: #126c72;
            --dp-teal-dark: #0b5358;
            --dp-navy: #203342;
            --dp-line: #d9e2e7;
            --dp-paper: #ffffff;
            --dp-canvas: #f4f7f6;
            --dp-mint: #eaf6f2;
            --dp-blue: #edf6f8;
            --dp-shadow: 0 10px 30px rgba(28, 51, 61, .07);
        }
        .stApp {
            background:
                radial-gradient(circle at 84% 4%, rgba(31, 142, 139, .08), transparent 24rem),
                var(--dp-canvas);
            color: var(--dp-ink);
        }
        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, .92) !important;
            color: var(--dp-ink) !important;
            border-bottom: 1px solid rgba(217, 226, 231, .85);
            backdrop-filter: blur(12px);
        }
        [data-testid="stToolbar"], [data-testid="stToolbar"] * {
            color: #172026 !important;
        }
        [data-testid="stDecoration"] {
            background: linear-gradient(90deg, var(--dp-teal), #2c9b91) !important;
        }
        .stApp p, .stApp li, .stApp label, .stApp span, .stApp div {
            color: var(--dp-ink);
        }
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at 10% 0%, rgba(80, 188, 174, .14), transparent 18rem),
                var(--dp-navy);
            border-right: 1px solid rgba(255, 255, 255, .08);
        }
        [data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }
        /*
         * Safari honors the broad sidebar text rule inside BaseWeb controls.
         * Give light form surfaces their own explicit foreground so entered
         * values, placeholders, upload actions, and alert copy stay legible.
         */
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            color: #172026 !important;
            -webkit-text-fill-color: #172026 !important;
            caret-color: var(--dp-teal-dark) !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: #6b7b84 !important;
            -webkit-text-fill-color: #6b7b84 !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="input"] svg,
        [data-testid="stSidebar"] [data-baseweb="textarea"] svg {
            color: #50636e !important;
            fill: #50636e !important;
        }
        [data-testid="stSidebar"] [data-testid="stDownloadButton"] button,
        [data-testid="stSidebar"] [data-testid="stDownloadButton"] button *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button *,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {
            color: #172026 !important;
        }
        [data-testid="stSidebar"] [data-testid="stAlert"] * {
            color: #3e3420 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            border-color: rgba(255, 255, 255, .18);
            background: rgba(255, 255, 255, .07);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            line-height: 1.45;
        }
        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 2px 0 14px;
        }
        .brand-mark {
            display: grid;
            place-items: center;
            width: 42px;
            height: 42px;
            flex: 0 0 42px;
            border-radius: 12px;
            background: linear-gradient(145deg, #49b9ab, #198080);
            box-shadow: 0 8px 20px rgba(0, 0, 0, .18);
            color: #ffffff !important;
            font-size: 14px;
            font-weight: 900;
            letter-spacing: .08em;
        }
        .brand-copy strong {
            display: block;
            color: #ffffff !important;
            font-size: 20px;
            line-height: 1.15;
            letter-spacing: -.02em;
        }
        .brand-copy span {
            display: block;
            margin-top: 3px;
            color: #bcd0d8 !important;
            font-size: 12px;
            letter-spacing: .03em;
        }
        .sidebar-trust {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            margin-bottom: 18px;
            border: 1px solid rgba(116, 217, 198, .3);
            border-radius: 999px;
            background: rgba(25, 128, 128, .18);
            padding: 6px 9px;
            color: #d9fff5 !important;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .sidebar-trust::before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #6ee7c6;
            box-shadow: 0 0 0 3px rgba(110, 231, 198, .12);
        }
        .main .block-container {
            max-width: 1240px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 1rem;
        }
        h1, h2, h3 {
            color: var(--dp-ink) !important;
            letter-spacing: -.025em;
        }
        h1 {
            font-size: clamp(2rem, 3.6vw, 3.15rem) !important;
            line-height: 1.05 !important;
        }
        .stButton button {
            min-height: 46px;
            border-radius: 10px;
            border: 1px solid #bdcbd2;
            background: var(--dp-paper);
            color: var(--dp-ink);
            font-weight: 700;
            box-shadow: 0 2px 7px rgba(28, 51, 61, .04);
            transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
        }
        .stButton button:hover {
            transform: translateY(-1px);
            border-color: var(--dp-teal);
            color: var(--dp-teal-dark);
            box-shadow: 0 7px 18px rgba(28, 51, 61, .1);
        }
        .stButton button[kind="primary"] {
            background: linear-gradient(135deg, var(--dp-teal), #167f7d);
            border-color: var(--dp-teal);
            color: #ffffff;
            box-shadow: 0 7px 18px rgba(18, 108, 114, .18);
        }
        .stButton button[kind="primary"] * {
            color: #ffffff !important;
        }
        .stButton button[kind="primary"]:hover {
            color: #ffffff;
            border-color: var(--dp-teal-dark);
            box-shadow: 0 10px 24px rgba(18, 108, 114, .24);
        }
        .stButton button:focus-visible {
            outline: 3px solid rgba(44, 155, 145, .28);
            outline-offset: 2px;
        }
        [data-testid="stMetric"] {
            min-height: 118px;
            background: var(--dp-paper);
            border: 1px solid var(--dp-line);
            border-radius: 13px;
            padding: 15px 16px;
            box-shadow: 0 5px 18px rgba(28, 51, 61, .045);
        }
        [data-testid="stMetric"] * {
            color: #172026 !important;
        }
        [data-testid="stMetricDelta"] div {
            color: #1b7a58 !important;
        }
        .hero {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at 92% 0%, rgba(53, 166, 154, .13), transparent 20rem),
                var(--dp-paper);
            border: 1px solid var(--dp-line);
            border-radius: 18px;
            padding: clamp(22px, 3.2vw, 38px);
            margin-bottom: .4rem;
            box-shadow: var(--dp-shadow);
        }
        .hero::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 5px;
            background: linear-gradient(180deg, #2da698, var(--dp-teal-dark));
        }
        .hero-topline {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 18px;
        }
        .eyebrow {
            color: var(--dp-teal) !important;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
        }
        .trust-badge {
            display: inline-flex;
            align-items: center;
            border: 1px solid #b9ddd6;
            border-radius: 999px;
            background: var(--dp-mint);
            padding: 6px 10px;
            color: var(--dp-teal-dark) !important;
            font-size: 11px;
            font-weight: 800;
            white-space: nowrap;
        }
        .hero h1 {
            max-width: 760px;
            margin: 0 0 12px;
        }
        .hero-copy {
            max-width: 760px;
            margin: 0 0 22px;
            color: #50636e !important;
            font-size: 17px;
            line-height: 1.55;
        }
        .case-file {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin-top: 8px;
        }
        .file-card {
            border: 1px solid #dce6e9;
            border-radius: 13px;
            padding: 16px;
            background: rgba(248, 251, 251, .88);
            color: var(--dp-ink);
            min-height: 124px;
        }
        .file-card span {
            display: block;
            color: var(--dp-muted) !important;
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .07em;
            margin-bottom: 8px;
        }
        .file-card strong {
            display: block;
            color: var(--dp-ink);
            font-size: 18px;
            line-height: 1.3;
            margin-bottom: 6px;
        }
        .file-card p {
            margin: 0;
            color: #5b6d77 !important;
            font-size: 13px;
            line-height: 1.45;
        }
        .bottom-line {
            border: 1px solid #bcded2;
            border-left: 6px solid var(--dp-teal);
            border-radius: 14px;
            background: var(--dp-mint);
            padding: 18px 20px;
            margin: 18px 0 6px;
            box-shadow: 0 5px 18px rgba(28, 51, 61, .045);
        }
        .bottom-line h2 {
            margin: 0 0 8px;
        }
        .bottom-line p {
            margin: 0;
            color: #23313a !important;
            font-size: 16px;
        }
        .run-card {
            border: 1px solid var(--dp-line);
            border-top: 4px solid var(--dp-teal);
            border-radius: 13px;
            padding: 14px 16px 16px;
            background: var(--dp-paper);
            min-height: 122px;
            color: var(--dp-ink);
            box-shadow: 0 5px 18px rgba(28, 51, 61, .045);
        }
        .run-card strong {
            display: block;
            font-size: 15px;
            margin-bottom: 6px;
            color: #172026;
        }
        .run-card span {
            color: var(--dp-teal) !important;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 800;
            letter-spacing: .06em;
        }
        .run-card div {
            color: #23313a !important;
            font-size: 13px;
            line-height: 1.35;
        }
        .claim-card {
            border: 1px solid var(--dp-line);
            border-radius: 13px;
            background: var(--dp-paper);
            padding: 17px;
            min-height: 230px;
            color: var(--dp-ink);
            box-shadow: 0 5px 18px rgba(28, 51, 61, .045);
        }
        .claim-card h3 {
            margin: 0 0 8px;
            font-size: 18px;
            color: #172026 !important;
        }
        .claim-card strong {
            display: block;
            font-size: 21px;
            margin-bottom: 10px;
            color: #172026;
        }
        .claim-card div, .claim-card li {
            color: #23313a !important;
        }
        .source-pill {
            display: inline-flex;
            align-items: center;
            border: 1px solid #cbdde2;
            border-radius: 999px;
            padding: 5px 9px;
            margin: 4px 5px 1px 0;
            font-size: 12px;
            background: var(--dp-blue);
            color: var(--dp-teal-dark) !important;
            font-weight: 700;
        }
        .status-note {
            border: 1px solid #bcded2;
            border-radius: 11px;
            padding: 13px 15px;
            background: var(--dp-mint);
            color: #267455 !important;
            font-weight: 700;
        }
        .review-box {
            border: 1px solid var(--dp-line);
            border-radius: 13px;
            background: var(--dp-paper);
            padding: 16px;
            margin-bottom: 10px;
            box-shadow: 0 5px 18px rgba(28, 51, 61, .04);
        }
        .review-box p {
            color: #23313a !important;
        }
        code {
            color: #176d8a !important;
            background: #eef7fb !important;
            border-radius: 4px;
            padding: 1px 4px;
        }
        .action-note {
            background: var(--dp-blue);
            border: 1px solid #c8dbe7;
            border-radius: 11px;
            padding: 11px 14px;
            min-height: 46px;
        }
        .action-note p {
            margin: 0;
            color: #23313a !important;
        }
        .qwen-progress {
            background: var(--dp-paper);
            border: 1px solid var(--dp-line);
            border-radius: 11px;
            padding: 13px 15px;
        }
        [data-baseweb="tab-list"] {
            gap: 6px;
            padding: 5px;
            border: 1px solid var(--dp-line);
            border-radius: 13px;
            background: rgba(255, 255, 255, .75);
        }
        button[data-baseweb="tab"] {
            min-height: 42px;
            border-radius: 9px;
            padding-left: 14px;
            padding-right: 14px;
            font-weight: 700;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: var(--dp-paper);
            box-shadow: 0 2px 9px rgba(28, 51, 61, .08);
        }
        [data-baseweb="tab-highlight"] {
            background-color: var(--dp-teal) !important;
        }
        [data-testid="stExpander"] {
            overflow: hidden;
            border-color: var(--dp-line);
            border-radius: 11px;
            background: rgba(255, 255, 255, .76);
        }
        [data-testid="stForm"] {
            border-color: var(--dp-line);
            border-radius: 14px;
            background: rgba(255, 255, 255, .58);
            box-shadow: 0 5px 18px rgba(28, 51, 61, .035);
        }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        textarea {
            border-radius: 9px !important;
        }
        @media (max-width: 760px) {
            .main .block-container {
                padding-top: 1.25rem;
            }
            .hero {
                border-radius: 14px;
                padding: 21px 18px 20px;
            }
            .hero-topline {
                align-items: flex-start;
                flex-direction: column;
                margin-bottom: 14px;
            }
            .hero-copy {
                font-size: 15px;
            }
            .case-file {
                grid-template-columns: 1fr;
            }
            [data-baseweb="tab-list"] {
                overflow-x: auto;
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_payload_with_progress(
    st: Any, *, use_qwen: bool, payload_builder=None
) -> Any:
    build = payload_builder or (lambda live: build_run_payload(use_qwen=live))
    if not use_qwen:
        with st.spinner("Reviewing IEP and service logs..."):
            return build(False)

    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def worker() -> None:
        try:
            result_queue.put(("ok", build(True)))
        except Exception as exc:  # noqa: BLE001 - surfaced in UI
            result_queue.put(("error", exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    messages = [
        "Connecting to Qwen Cloud...",
        "Reading the IEP service line...",
        "Classifying missed-session reasons...",
        "Running the deterministic ledger locally...",
        "Grounding claims to IEP, logs, and legal authorities...",
        "Drafting the complaint narrative and holding it for approval...",
    ]
    progress = st.progress(0, text=messages[0])
    detail = st.empty()
    started = time.perf_counter()
    index = 0
    while thread.is_alive():
        elapsed = int(time.perf_counter() - started)
        progress.progress(min(92, 12 + index * 13), text=messages[index % len(messages)])
        detail.markdown(
            f'<div class="qwen-progress"><b>Live Qwen review is running.</b><br>'
            f'Elapsed: {elapsed}s. The app is attempting Qwen for language tasks; '
            'the completed run will disclose successful calls and any fallback.</div>',
            unsafe_allow_html=True,
        )
        index += 1
        time.sleep(1.5)

    status, value = result_queue.get()
    progress.progress(100, text="Qwen review complete.")
    detail.empty()
    if status == "error":
        raise value
    return value


def _render_step(st: Any, step: dict[str, str]) -> None:
    owner = html.escape(str(step["owner"]))
    label = html.escape(str(step["label"]))
    detail = html.escape(str(step["detail"]))
    st.markdown(
        f"""
        <div class="run-card">
          <span>{owner}</span>
          <strong>{label}</strong>
          <div>{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_claim(st: Any, claim: dict[str, Any]) -> None:
    law = "".join(
        f'<span class="source-pill">{html.escape(str(item))}</span>'
        for item in claim["law"][:5])
    logs = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in claim["logs"][:5])
    title = html.escape(str(claim["title"]))
    finding = html.escape(str(claim["finding"]))
    iep = html.escape(str(claim["iep"]))
    st.markdown(
        f"""
        <div class="claim-card">
          <h3>{title}</h3>
          <strong>{finding}</strong>
          <div><b>IEP</b>: {iep}</div>
          <div style="margin-top:8px;"><b>Log evidence</b><ul>{logs}</ul></div>
          <div style="margin-top:8px;">{law}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_app() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="Due Process Agent Desk",
        page_icon="DP",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css(st)

    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="brand-mark">DP</div>
          <div class="brand-copy">
            <strong>Due Process</strong>
            <span>IEP evidence operations</span>
          </div>
        </div>
        <div class="sidebar-trust">Qwen Cloud · human controlled</div>
        """,
        unsafe_allow_html=True,
    )
    data_source = st.sidebar.radio(
        "Case source", ["Synthetic worked example", "Upload redacted case"],
        help="Use only synthetic or already-redacted records in this public demo.")
    upload_mode = data_source == "Upload redacted case"

    uploaded_csv_text = ""
    csv_upload = None
    if upload_mode:
        st.sidebar.markdown("**Redacted case details**")
        student_name = st.sidebar.text_input(
            "Student label", REDACTED_CASE_STUDENT)
        school_name = st.sidebar.text_input(
            "School label", REDACTED_CASE_SCHOOL)
        district_name = st.sidebar.text_input(
            "District label", REDACTED_CASE_DISTRICT)
        state = st.sidebar.text_input("State code", "", max_chars=2).upper()
        periods = st.sidebar.number_input(
            "Instructional periods", min_value=1, max_value=60,
            value=REDACTED_CASE_PERIODS)
        window_start = st.sidebar.date_input(
            "Window start", REDACTED_CASE_START)
        window_end = st.sidebar.date_input(
            "Window end", REDACTED_CASE_END)
        iep_input = st.sidebar.text_area(
            "IEP services text",
            REDACTED_CASE_IEP_TEXT,
            height=145,
        )
        with st.sidebar.expander("Redacted demo case kit", expanded=True):
            st.caption(
                "Fully synthetic and de-identified. Download this service log, "
                "then upload it below to exercise the real intake path.")
            st.download_button(
                "Download redacted service log",
                data=REDACTED_CASE_LOG_CSV,
                file_name="redacted-service-log-r104.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Download supporting provider note",
                data=REDACTED_CASE_PROVIDER_NOTE,
                file_name="redacted-provider-note-r104.txt",
                mime="text/plain",
                use_container_width=True,
            )
        csv_upload = st.sidebar.file_uploader(
            "Service log CSV", type=["csv", "tsv"])
        if csv_upload is not None:
            try:
                uploaded_csv_text = csv_upload.getvalue().decode("utf-8-sig")
            except UnicodeDecodeError:
                st.sidebar.error("The service log must be UTF-8 CSV/TSV text.")
        with st.sidebar.expander("Expected CSV columns"):
            st.code(
                "Date,Minutes,Status,Reason,Provider\n"
                "2026-01-08,0,Missed,Provider absent no substitute,")
        st.sidebar.warning(
            "Do not upload identifiable student records to the public demo. "
            "Cloud vision rejects unredacted images.")
        data_attested = st.sidebar.checkbox(
            "I confirm these records are synthetic or already de-identified",
            value=False,
        )
    else:
        student_name = "A. Doe"
        school_name = "Maple Elementary"
        district_name = "Springfield SD"
        state = ""
        periods = 36
        window_start = date(TODAY.year - 1, 9, 1)
        window_end = TODAY
        iep_input = ""
        data_attested = True
        st.sidebar.markdown("**Case file**")
        st.sidebar.write("Student: A. Doe")
        st.sidebar.write("School: Maple Elementary")
        st.sidebar.write("District: Springfield SD")
    st.sidebar.divider()
    st.sidebar.markdown("**Guardrails**")
    st.sidebar.write("No legal advice.")
    st.sidebar.write("No outbound send without human approval.")
    st.sidebar.write("Every finding is tied to source records.")

    hero_promise = (
        html.escape(iep_input.strip()[:100]) if upload_mode
        else "Speech-language therapy · 3x/week · 30 minutes")
    hero_records = (
        html.escape(csv_upload.name) if upload_mode and csv_upload is not None
        else ("Awaiting redacted CSV" if upload_mode else "108 synthetic log rows"))
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-topline">
            <span class="eyebrow">Case review workspace</span>
            <span class="trust-badge">AI-assisted · deterministically verified</span>
          </div>
          <h1>IEP service delivery, reconciled.</h1>
          <p class="hero-copy">Turn service commitments and delivery records into a traceable evidence packet, with deterministic calculations and a human checkpoint before every external action.</p>
          <div class="case-file">
            <div class="file-card"><span>IEP service text</span><strong>{hero_promise}</strong><p>Qwen or rules extract a structured commitment.</p></div>
            <div class="file-card"><span>Records</span><strong>{hero_records}</strong><p>Delivered, excused, and missed sessions are reconciled.</p></div>
            <div class="file-card"><span>Safe next step</span><strong>Human-review draft</strong><p>No external action occurs without explicit approval.</p></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "run_payload" not in st.session_state:
        st.session_state.run_payload = None
    if "prepared_review" not in st.session_state:
        st.session_state.prepared_review = None
    if "approval_reviewed" not in st.session_state:
        st.session_state.approval_reviewed = False
    action_col, mode_col, proof_col = st.columns([1.2, 1.0, 2.3])
    with action_col:
        run_qwen = st.button("Start Qwen review", type="primary", use_container_width=True)
    with mode_col:
        run_preview = st.button("Preview without cloud", use_container_width=True)
    with proof_col:
        st.markdown(
            '<div class="action-note"><p>The primary demo runs through Qwen Cloud and streams progress. The local preview is a rehearsal path that uses the same ledger and approval gates without cloud latency.</p></div>',
            unsafe_allow_html=True,
        )

    if run_qwen or run_preview:
        if upload_mode and (not iep_input.strip() or not uploaded_csv_text.strip()):
            st.error("Add the redacted IEP services text and a service-log CSV first.")
        elif upload_mode and window_end < window_start:
            st.error("Window end must be on or after window start.")
        elif upload_mode and not data_attested:
            st.error(
                "Confirm that the records are synthetic or already de-identified.")
        else:
            def review_builder(live: bool):
                if upload_mode:
                    delimiter = (
                        "\t" if csv_upload is not None
                        and csv_upload.name.lower().endswith(".tsv") else None)
                    logs = load_logs_csv(
                        uploaded_csv_text, "uploaded-service",
                        delimiter=delimiter,
                        source_uri="uploaded://service-log.csv",
                    )
                    if not logs:
                        raise ValueError(
                            "The uploaded log contains no parseable dated rows.")
                    return prepare_case_review(
                        iep_text=iep_input,
                        logs=logs,
                        window_start=window_start,
                        window_end=window_end,
                        instructional_periods=int(periods),
                        context=LetterContext(
                            student_name=student_name,
                            school_name=school_name,
                            district_name=district_name,
                            state_agency_name=(
                                f"{state} State Education Agency"
                                if state else "State Education Agency"),
                            state=state,
                            letter_date=TODAY,
                        ),
                        use_qwen=live,
                        state=state,
                        include_systemic_demo=False,
                    )
                scenario = worked_example_speech(classified=False)
                return prepare_case_review(
                    iep_text=scenario.iep_text,
                    logs=scenario.logs,
                    window_start=scenario.window_start,
                    window_end=scenario.window_end,
                    instructional_periods=scenario.instructional_periods,
                    context=LetterContext(
                        student_name="A. Doe",
                        parent_name="J. Doe",
                        school_name="Maple Elementary",
                        district_name="Springfield SD",
                        state_agency_name="State Education Agency",
                        letter_date=TODAY,
                    ),
                    use_qwen=live,
                    include_systemic_demo=True,
                )

            st.session_state.approval_reviewed = False
            st.session_state.run_payload = None
            try:
                st.session_state.prepared_review = _run_payload_with_progress(
                    st, use_qwen=run_qwen,
                    payload_builder=review_builder)
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    payload = st.session_state.run_payload
    review = st.session_state.prepared_review
    if review is not None and payload is None:
        commitment = review.commitment
        st.markdown("### Human checkpoint 1 — confirm Qwen's interpretation")
        st.caption(
            "Edit any field that does not match the source IEP. Deterministic "
            "analysis remains blocked until this form is confirmed.")
        with st.form("confirm-commitment-and-reasons"):
            form_cols = st.columns(3)
            with form_cols[0]:
                service_type_value = st.selectbox(
                    "Service type",
                    options=[item.value for item in ServiceType],
                    index=[item.value for item in ServiceType].index(
                        commitment.service_type.value),
                    format_func=lambda value: value.replace("_", " ").title(),
                )
                frequency_value = st.number_input(
                    "Sessions per period", min_value=1, max_value=20,
                    value=commitment.frequency_count)
            with form_cols[1]:
                period_value = st.selectbox(
                    "Frequency period",
                    options=[item.value for item in FrequencyPeriod],
                    index=[item.value for item in FrequencyPeriod].index(
                        commitment.frequency_period.value),
                    format_func=str.title,
                )
                duration_value = st.number_input(
                    "Minutes per session", min_value=1, max_value=480,
                    value=commitment.duration_minutes)
            with form_cols[2]:
                setting_value = st.selectbox(
                    "Setting",
                    options=[item.value for item in DeliverySetting],
                    index=[item.value for item in DeliverySetting].index(
                        commitment.setting.value),
                    format_func=str.title,
                )
                location_options = [""] + [
                    item.value for item in ServiceLocation]
                location_value = st.selectbox(
                    "Location",
                    options=location_options,
                    index=(location_options.index(commitment.location.value)
                           if commitment.location else 0),
                    format_func=lambda value: (
                        "Not specified" if not value
                        else value.replace("_", " ").title()),
                )
                group_size_value = st.number_input(
                    "Maximum group size (0 = unspecified)",
                    min_value=0,
                    max_value=50,
                    value=commitment.group_size_max or 0,
                )

            ambiguity_rows = review.ambiguity_rows()
            decisions: dict[str, str] = {}
            if ambiguity_rows:
                st.markdown("#### Human checkpoint 2 — resolve ambiguity")
                st.caption(
                    "Qwen/rules refused to guess. Review the source record and "
                    "choose how each session should be treated.")
                for row in ambiguity_rows:
                    left, right = st.columns([2.2, 1])
                    with left:
                        st.markdown(
                            f"**{html.escape(row['date'])} · "
                            f"{html.escape(row['reason'])}**")
                        st.caption(
                            f"{row['method']} · confidence "
                            f"{row['confidence']:.0%} · {row['rationale']}")
                    with right:
                        decisions[row["id"]] = st.selectbox(
                            "Human decision",
                            options=["", ExcusedClass.EXCUSED.value,
                                     ExcusedClass.UNEXCUSED.value],
                            key=f"ambiguity-{row['id']}",
                            format_func=lambda value: {
                                "": "Choose…",
                                "excused": "Excused",
                                "unexcused": "Unexcused",
                            }[value],
                        )
            else:
                st.success(
                    "No ambiguous missed-session reasons require resolution.")

            source_confirmed = st.checkbox(
                "I compared these values and decisions with the source records")
            confirm_review = st.form_submit_button(
                "Confirm inputs and run deterministic analysis",
                type="primary",
                use_container_width=True,
            )

        if confirm_review:
            if not source_confirmed:
                st.error("Confirm that you reviewed the source records first.")
                st.stop()
            try:
                with st.spinner(
                    "Running deterministic ledger and grounding claims..."):
                    st.session_state.run_payload = finalize_case_review(
                        review,
                        service_type=service_type_value,
                        frequency_count=int(frequency_value),
                        frequency_period=period_value,
                        duration_minutes=int(duration_value),
                        setting=setting_value,
                        location=location_value,
                        group_size_max=int(group_size_value),
                        ambiguity_decisions=decisions,
                    )
                st.session_state.prepared_review = None
                payload = st.session_state.run_payload
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
                st.stop()
        else:
            st.stop()

    if payload is None:
        st.markdown("### What happens when you start the review")
        cols = st.columns(4)
        preview_steps = [
            ("1", "Read the IEP", "Extract the promised service schedule."),
            ("2", "Review logs", "Classify missed and excused sessions."),
            ("3", "Run the ledger", "Compute delivered vs required minutes."),
            ("4", "Prepare next step", "Draft evidence-backed remedy for review."),
        ]
        for col, (num, title, body) in zip(cols, preview_steps):
            with col:
                st.markdown(
                    f'<div class="run-card"><span>Step {num}</span><strong>{title}</strong><div>{body}</div></div>',
                    unsafe_allow_html=True,
                )
        st.stop()

    case = payload["case"]
    ledger = payload["ledger"]
    det = payload["deterministic"]
    mode_label = {
        "qwen-online": "verified Qwen Cloud outputs",
        "mixed-fallback": "Qwen attempted with an explicit local fallback",
        "offline-fallback": "local deterministic preview",
    }[payload["mode"]]
    student_label = html.escape(str(case["student"]))
    if det["material"]:
        bottom_heading = "Review signal: a substantial service gap needs human review"
        bottom_detail = (
            f'{student_label} was promised {ledger["required_sessions"]} sessions. '
            f'The records show {ledger["delivered_sessions"]} delivered and '
            f'{ledger["unexcused_minutes"]:,} unexcused minutes '
            f'({ledger["shortfall_pct"]}). The product threshold is a screening '
            "signal, not a legal finding.")
    else:
        bottom_heading = "No actionable implementation signal was generated"
        bottom_detail = (
            f'{student_label}: {ledger["delivered_sessions"]} delivered sessions '
            f'and {ledger["unexcused_minutes"]:,} unexcused minutes. Keep monitoring '
            "and have a human review incomplete or ambiguous records.")
    st.markdown(
        f"""
        <div class="bottom-line">
          <h2>{bottom_heading}</h2>
          <p>{bottom_detail}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="status-note">Review completed in {payload["duration_ms"]}ms using {mode_label}. Human approval is still required before any outbound action.</div>',
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(6)
    metric_cols[0].metric("Required", _minutes(ledger["required_minutes"]), f'{ledger["required_sessions"]} sessions')
    metric_cols[1].metric("Delivered", _minutes(ledger["delivered_minutes"]), f'{ledger["delivered_sessions"]} sessions')
    metric_cols[2].metric("Unexcused gap", _minutes(ledger["unexcused_minutes"]), ledger["shortfall_pct"])
    metric_cols[3].metric("Comp estimate", _minutes(ledger["comp_minutes"]), f'{ledger["comp_hours"]} hours')
    deadline_delta = (f'{det["state_days_remaining"]} days left'
                      if det["state_days_remaining"] is not None
                      else "no allegation")
    metric_cols[4].metric("Event deadline", det["state_deadline"], deadline_delta)
    metric_cols[5].metric(
        "Review signal", "Yes" if det["material"] else "No", "policy threshold")

    st.subheader("What the agent did")
    step_cols = st.columns(3)
    for index, step in enumerate(payload["agent_steps"]):
        with step_cols[index % 3]:
            _render_step(st, step)

    tabs = st.tabs(["Review Summary", "Evidence Packet", "Human Approval", "Community Pattern", "Technical Proof"])

    with tabs[0]:
        safe_service = html.escape(str(case["service"]))
        safe_iep_text = html.escape(str(case["iep_text"]))
        safe_window = html.escape(str(case["window"]))
        safe_reason = html.escape(str(det["materiality_reason"]))
        left, right = st.columns(2)
        with left:
            st.markdown("### What was promised")
            st.markdown(
                f"""
                <div class="review-box">
                  <p><b>Service:</b> {safe_service}</p>
                  <p><b>IEP text:</b> {safe_iep_text}</p>
                  <p><b>Review window:</b> {safe_window}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right:
            st.markdown("### What the records show")
            st.markdown(
                f"""
                <div class="review-box">
                  <p><b>Logs reviewed:</b> {case["logs"]}</p>
                  <p><b>Missed logs:</b> {case["missed_logs"]}</p>
                  <p><b>Review rule:</b> {safe_reason}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tabs[1]:
        st.markdown("### Evidence packet")
        st.caption("Each claim is tied to the IEP text, service log rows, and legal authorities.")
        claim_cols = st.columns(2)
        for index, claim in enumerate(payload["claims"]):
            with claim_cols[index % 2]:
                _render_claim(st, claim)
        if payload["draft"]["packet"]:
            st.download_button(
                "Download evidence packet",
                data=payload["draft"]["packet"],
                file_name="due-process-evidence-packet.txt",
                mime="text/plain",
            )

    with tabs[2]:
        st.markdown("### Human approval gate")
        st.caption("This is not a send button. It is a review checklist for the human who must approve the record before any outbound action.")
        for checkpoint in payload["checkpoints"]:
            title = checkpoint["kind"].replace("_", " ").title()
            with st.expander(title, expanded=not checkpoint["resolved"]):
                st.write(checkpoint["description"])
                if checkpoint["kind"] == "approve_instrument":
                    st.write("Review the evidence packet and draft complaint in the adjacent tabs before marking this complete.")
                    reviewed_evidence = st.checkbox(
                        "I reviewed the evidence packet",
                        key=f"evidence-{checkpoint['kind']}",
                    )
                    reviewed_draft = st.checkbox(
                        "I reviewed the draft complaint text",
                        key=f"draft-{checkpoint['kind']}",
                    )
                    if st.button(
                        "Mark draft reviewed - do not send",
                        key=f"mark-{checkpoint['kind']}",
                        disabled=not (reviewed_evidence and reviewed_draft),
                    ):
                        st.session_state.approval_reviewed = True
                    if st.session_state.approval_reviewed:
                        st.success(
                            "Draft review recorded. No external action was taken.")
                    else:
                        st.warning("Outbound action remains blocked.")
                elif checkpoint["resolved"]:
                    st.success("Resolved and recorded in the audit trail.")
                else:
                    st.warning("Awaiting human decision.")

        st.caption(
            "This workspace does not email, file, or upload the draft. Downloaded "
            "packets remain under the reviewer's control.")

    with tabs[3]:
        st.markdown("### District-wide pattern")
        systemic = payload["systemic"]
        if systemic is None:
            st.info(
                "Cohort aggregation is disabled for uploaded cases. It belongs "
                "in an authorized advocate workspace with enough cases to pass "
                "the privacy gate.")
        else:
            st.caption(
                "Synthetic cohort: a privacy-gated signal for broader human investigation.")
            sys_cols = st.columns(4)
            sys_cols[0].metric("Students", systemic["students_with_service"])
            sys_cols[1].metric("Review signals", systemic["students_material"])
            sys_cols[2].metric("Affected", systemic["share_material"])
            sys_cols[3].metric("Aggregate gap", systemic["aggregate_gap_label"])
            st.success(
                f"Synthetic cohort passed the k >= {systemic['k_threshold']} "
                "reporting gate; no student names are shown.")
            with st.expander("Draft request for systemic review"):
                st.text(systemic["draft_preview"])

    with tabs[4]:
        st.markdown("### Technical proof")
        st.caption("This section is for judges and engineers. It is not the primary parent-facing workflow.")
        proof_a, proof_b = st.columns(2)
        with proof_a:
            st.markdown("#### Bounded Qwen")
            st.write(f"Extraction method: `{payload['qwen']['extraction_method']}`")
            st.write(f"Classification methods: `{payload['qwen']['classification_methods']}`")
            st.write(f"Models: `{payload['qwen']['orchestrator_model']}` / `{payload['qwen']['workhorse_model']}`")
            st.write(f"Qwen output used: `{payload['qwen']['used_for_output']}`")
            with st.expander("Per-call provenance"):
                st.json(payload["qwen"]["traces"])
        with proof_b:
            st.markdown("#### Deterministic core")
            st.write(payload["deterministic"]["materiality_reason"])
            st.write(f"Due process deadline: `{payload['deterministic']['due_process_deadline']}`")
            st.write("Grounding rejects claims without real IEP, log, and legal references.")
        draft_col, audit_col = st.columns([1.3, 1])
        with draft_col:
            st.markdown("### Human-review draft")
            st.text(payload["draft"]["text"])
        with audit_col:
            st.markdown("### Backend audit trail")
            st.code("\n".join(payload["audit"]))
            with st.expander("Raw payload"):
                st.json(payload)


def main() -> None:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            print("Run this demo with:")
            print("  streamlit run src/due_process/examples/case_desk.py")
            return
        render_app()
    except ModuleNotFoundError as exc:
        if exc.name != "streamlit":
            raise
        print("Streamlit is not installed. Install with: uv pip install -e \".[demo]\"")
        print("Then run: streamlit run src/due_process/examples/case_desk.py")


if __name__ == "__main__":
    main()
