"""Streamlit advocate case desk for the Due Process demo.

Run:
    streamlit run src/due_process/examples/case_desk.py

The UI is a presentation layer over the real backend workflow: Qwen extraction
and classification when configured, deterministic ledger analysis, evidence
grounding, draft generation, human checkpoints, and systemic aggregation.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import date, datetime
from typing import Any

from due_process.agent import ApprovalPolicy, run_enforcement
from due_process.analysis import analyze_commitment
from due_process.instruments.drafter import LetterContext, draft_systemic_complaint
from due_process.llm.client import default_client
from due_process.models import LogStatus
from due_process.scenarios import district_caseload, worked_example_speech
from due_process.systemic import StudentCase, aggregate_systemic

TODAY = date(2026, 6, 30)
NOW = datetime(2026, 6, 30, 9, 0, 0)


class DraftOnlyDemoPolicy(ApprovalPolicy):
    """Confirm inputs and draft a remedy, but never approve sending."""

    name = "draft-only demo"

    def confirm_commitments(self, extracted):
        return True


def _minutes(value: int) -> str:
    return f"{value:,} min"


def _pct(value) -> str:
    return f"{value:.1%}"


def _method_counts(items: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items.values():
        counts[item.method] = counts.get(item.method, 0) + 1
    return counts


def build_run_payload(*, use_qwen: bool = True) -> dict[str, Any]:
    """Execute the real demo workflow and return a JSON-safe payload."""
    started = time.perf_counter()
    scenario = worked_example_speech(classified=False)
    client = default_client() if use_qwen else None
    qwen_available = client is not None and client.available
    context = LetterContext(
        student_name="A. Doe",
        parent_name="J. Doe",
        school_name="Maple Elementary",
        district_name="Springfield SD",
        state_agency_name="State Education Agency",
        letter_date=TODAY,
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
        policy=DraftOnlyDemoPolicy(),
    )
    analysis = run.analyses[0]
    ledger = analysis.ledger
    deadline = analysis.deadlines[0]
    due_process_deadline = analysis.due_process_deadlines[0]
    draft = run.instruments[0]
    bundle = analysis.bundles[0]

    district, students, ws, we, periods = district_caseload()
    district_cases: list[StudentCase] = []
    for sid, commitment, logs in students:
        district_analysis = analyze_commitment(
            commitment,
            logs,
            window_start=ws,
            window_end=we,
            today=TODAY,
            instructional_periods=periods,
        )
        district_cases.append(
            StudentCase(student_id=sid, district=district, analyses=[district_analysis])
        )
    findings = aggregate_systemic(district_cases)
    finding = findings[0]
    systemic_draft = draft_systemic_complaint(
        findings,
        LetterContext(
            parent_name="Parent Coalition",
            district_name=district,
            state_agency_name="State Education Agency",
            letter_date=TODAY,
        ),
    )

    comp_minutes = analysis.compensatory.estimated_minutes if analysis.compensatory else 0
    class_counts = _method_counts(run.classification.classifications if run.classification else {})
    extracted_method = run.extracted[0].method if run.extracted else "none"
    missed_count = sum(1 for log in scenario.logs if log.status == LogStatus.MISSED)
    duration_ms = int((time.perf_counter() - started) * 1000)

    return {
        "run_id": f"demo-{int(time.time())}",
        "status": "needs_human_approval" if run.needs_human else "complete",
        "mode": "qwen-online" if qwen_available else "offline-fallback",
        "duration_ms": duration_ms,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "case": {
            "student": "A. Doe",
            "school": "Maple Elementary",
            "district": "Springfield SD",
            "service": analysis.commitment.service_type.value.replace("_", " ").title(),
            "window": f"{ledger.window_start.isoformat()} to {ledger.window_end.isoformat()}",
            "iep_text": scenario.iep_text.strip(),
            "logs": len(scenario.logs),
            "missed_logs": missed_count,
        },
        "agent_steps": [
            {
                "label": "Read IEP",
                "owner": "Qwen" if qwen_available else "rules",
                "detail": f"{len(run.extracted)} commitment extracted by {extracted_method}.",
            },
            {
                "label": "Classify logs",
                "owner": "Qwen" if qwen_available else "rules",
                "detail": f"{len(run.classification.classifications)} missed/short reasons classified.",
            },
            {
                "label": "Run ledger",
                "owner": "deterministic",
                "detail": f"{ledger.required_sessions} required sessions reconciled against {len(scenario.logs)} logs.",
            },
            {
                "label": "Apply materiality",
                "owner": "deterministic",
                "detail": analysis.materiality.reasons[0],
            },
            {
                "label": "Ground claims",
                "owner": "deterministic",
                "detail": f"{len(bundle.log_refs)} log refs, {len(bundle.iep_refs)} IEP refs, {len(bundle.legal_provisions)} legal refs.",
            },
            {
                "label": "Draft remedy",
                "owner": "agent",
                "detail": "State complaint drafted and held for human approval.",
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
            "available": qwen_available,
            "extraction_method": extracted_method,
            "classification_methods": class_counts,
            "orchestrator_model": client.config.orchestrator_model if client else "none",
            "workhorse_model": client.config.workhorse_model if client else "none",
        },
        "deterministic": {
            "material": analysis.materiality.is_material,
            "materiality_reason": analysis.materiality.reasons[0],
            "state_deadline": deadline.sol_expiry_date.isoformat(),
            "state_days_remaining": deadline.days_remaining,
            "due_process_deadline": due_process_deadline.sol_expiry_date.isoformat(),
            "due_process_days_remaining": due_process_deadline.days_remaining,
        },
        "claims": [
            {
                "title": "Material implementation failure",
                "finding": f"{_minutes(ledger.unexcused_shortfall_minutes)} unexcused shortfall ({_pct(ledger.shortfall_pct)}).",
                "iep": bundle.iep_refs[0].cite() if bundle.iep_refs else "services line",
                "logs": [ref.cite() for ref in bundle.log_refs[:10]],
                "law": [p.short_label for p in bundle.legal_provisions],
            },
            {
                "title": "Draft remedy gated by a human",
                "finding": f"{_minutes(comp_minutes)} compensatory estimate; state complaint ready.",
                "iep": "Human approval required before send.",
                "logs": [f"State complaint deadline: {deadline.sol_expiry_date.isoformat()}"],
                "law": draft.citations,
            },
        ],
        "checkpoints": [
            {
                "kind": cp.kind,
                "description": cp.description,
                "resolved": cp.resolved,
                "pending": cp.pending_count,
            }
            for cp in run.checkpoints
        ],
        "systemic": {
            "district": finding.district,
            "service": finding.service_type.value.replace("_", " ").title(),
            "students_with_service": finding.n_students_with_service,
            "students_material": finding.n_students_material,
            "share_material": _pct(finding.material_student_share),
            "aggregate_gap": finding.total_unexcused_minutes,
            "aggregate_gap_label": _minutes(finding.total_unexcused_minutes),
            "k_threshold": finding.k_threshold,
            "draft_preview": systemic_draft.draft_text,
        },
        "audit": run.audit_lines(),
        "draft": {
            "type": draft.type.value,
            "status": draft.status.value,
            "citations": draft.citations,
            "text": draft.draft_text,
        },
    }


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f1e8;
            color: #18242b;
        }
        [data-testid="stHeader"] {
            background: #ffffff !important;
            color: #172026 !important;
            border-bottom: 1px solid #e1e7ee;
        }
        [data-testid="stToolbar"], [data-testid="stToolbar"] * {
            color: #172026 !important;
        }
        [data-testid="stDecoration"] {
            background: #176d8a !important;
        }
        .stApp p, .stApp li, .stApp label, .stApp span, .stApp div {
            color: #18242b;
        }
        [data-testid="stSidebar"] {
            background: #253442;
        }
        [data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }
        .main .block-container {
            max-width: 1280px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 1rem;
        }
        h1, h2, h3 {
            color: #172026 !important;
            letter-spacing: 0;
        }
        .stButton button {
            border-radius: 7px;
            border: 1px solid #b9c7d2;
            background: #ffffff;
            color: #18242b;
            font-weight: 700;
        }
        .stButton button[kind="primary"] {
            background: #176d8a;
            border-color: #176d8a;
            color: #ffffff;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            padding: 12px 14px;
        }
        [data-testid="stMetric"] * {
            color: #172026 !important;
        }
        [data-testid="stMetricDelta"] div {
            color: #1b7a58 !important;
        }
        .hero {
            background: #ffffff;
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            padding: 22px;
            margin-bottom: .25rem;
        }
        .case-file {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-top: 10px;
        }
        .file-card {
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            padding: 14px;
            background: #fbfcfd;
            color: #18242b;
            min-height: 116px;
        }
        .file-card span {
            display: block;
            color: #60717f !important;
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .file-card strong {
            display: block;
            color: #172026;
            font-size: 18px;
            margin-bottom: 6px;
        }
        .bottom-line {
            border: 1px solid #bcded2;
            border-left: 6px solid #267455;
            border-radius: 8px;
            background: #edf8f6;
            padding: 16px;
            margin: 16px 0 4px;
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
            border: 1px solid #d8e0e8;
            border-left: 5px solid #176d8a;
            border-radius: 8px;
            padding: 13px 14px;
            background: #ffffff;
            min-height: 118px;
            color: #172026;
        }
        .run-card strong {
            display: block;
            font-size: 15px;
            margin-bottom: 6px;
            color: #172026;
        }
        .run-card span {
            color: #60717f !important;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 800;
        }
        .run-card div {
            color: #23313a !important;
            font-size: 13px;
            line-height: 1.35;
        }
        .claim-card {
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            background: #fbfcfd;
            padding: 14px;
            min-height: 230px;
            color: #172026;
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
            display: inline-block;
            border: 1px solid #d8e0e8;
            border-radius: 999px;
            padding: 5px 8px;
            margin: 0 5px 5px 0;
            font-size: 12px;
            background: #ffffff;
            color: #176d8a !important;
            font-weight: 700;
        }
        .status-note {
            border: 1px solid #bcded2;
            border-radius: 8px;
            padding: 12px 14px;
            background: #edf8f6;
            color: #267455 !important;
            font-weight: 700;
        }
        .review-box {
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            background: #ffffff;
            padding: 14px;
            margin-bottom: 10px;
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
            background: #eef7fb;
            border: 1px solid #c8dbe7;
            border-radius: 8px;
            padding: 12px 14px;
            min-height: 42px;
        }
        .action-note p {
            margin: 0;
            color: #23313a !important;
        }
        .qwen-progress {
            background: #ffffff;
            border: 1px solid #d8e0e8;
            border-radius: 8px;
            padding: 12px 14px;
        }
        @media (max-width: 760px) {
            .case-file {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_payload_with_progress(st: Any, *, use_qwen: bool) -> dict[str, Any]:
    if not use_qwen:
        with st.spinner("Reviewing IEP and service logs..."):
            return build_run_payload(use_qwen=False)

    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def worker() -> None:
        try:
            result_queue.put(("ok", build_run_payload(use_qwen=True)))
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
            f'Elapsed: {elapsed}s. Qwen is handling the language-heavy extraction and classification while the deterministic ledger stays local.</div>',
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
    st.markdown(
        f"""
        <div class="run-card">
          <span>{step["owner"]}</span>
          <strong>{step["label"]}</strong>
          <div>{step["detail"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_claim(st: Any, claim: dict[str, Any]) -> None:
    law = "".join(f'<span class="source-pill">{item}</span>' for item in claim["law"][:5])
    logs = "".join(f"<li>{item}</li>" for item in claim["logs"][:5])
    st.markdown(
        f"""
        <div class="claim-card">
          <h3>{claim["title"]}</h3>
          <strong>{claim["finding"]}</strong>
          <div><b>IEP</b>: {claim["iep"]}</div>
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

    st.sidebar.title("Due Process")
    st.sidebar.caption("IEP service-delivery review")
    st.sidebar.markdown("**Case file**")
    st.sidebar.write("Student: A. Doe")
    st.sidebar.write("School: Maple Elementary")
    st.sidebar.write("District: Springfield SD")
    st.sidebar.divider()
    st.sidebar.markdown("**Guardrails**")
    st.sidebar.write("No legal advice.")
    st.sidebar.write("No outbound send without human approval.")
    st.sidebar.write("Every finding is tied to source records.")

    st.markdown(
        """
        <div class="hero">
          <h1>IEP Service Delivery Review</h1>
          <p>Check whether the school delivered the services written into the IEP, what is owed if it did not, and what evidence supports the next step.</p>
          <div class="case-file">
            <div class="file-card"><span>IEP promise</span><strong>Speech-language therapy</strong><p>3x per week, 30 minutes, individual pull-out.</p></div>
            <div class="file-card"><span>Records received</span><strong>108 service log rows</strong><p>Delivered, excused, and missed sessions are reviewed.</p></div>
            <div class="file-card"><span>Safe next step</span><strong>Draft only</strong><p>The agent can draft a complaint, but a human must approve it.</p></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "run_payload" not in st.session_state:
        st.session_state.run_payload = None
    if "approval_reviewed" not in st.session_state:
        st.session_state.approval_reviewed = False

    action_col, mode_col, proof_col = st.columns([1.2, 1.0, 2.3])
    with action_col:
        run_qwen = st.button("Run live Qwen review", type="primary", use_container_width=True)
    with mode_col:
        run_preview = st.button("Fast local preview", use_container_width=True)
    with proof_col:
        st.markdown(
            '<div class="action-note"><p>The primary demo runs through Qwen Cloud and streams progress. The local preview is a rehearsal path that uses the same ledger and approval gates without cloud latency.</p></div>',
            unsafe_allow_html=True,
        )

    if run_qwen or run_preview:
        st.session_state.approval_reviewed = False
        st.session_state.run_payload = _run_payload_with_progress(st, use_qwen=run_qwen)

    payload = st.session_state.run_payload
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
    mode_label = "Qwen Cloud review" if payload["mode"] == "qwen-online" else "local deterministic preview"
    st.markdown(
        f"""
        <div class="bottom-line">
          <h2>Bottom line: material service gap found</h2>
          <p>{case["student"]} was promised {ledger["required_sessions"]} sessions. The logs show {ledger["delivered_sessions"]} delivered, leaving {ledger["unexcused_minutes"]:,} unexcused minutes ({ledger["shortfall_pct"]}) and an estimated {ledger["comp_hours"]} hours of compensatory services. The complaint is drafted, but not approved to send.</p>
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
    metric_cols[4].metric("State deadline", det["state_deadline"], f'{det["state_days_remaining"]} days left')
    metric_cols[5].metric("Material", "Yes" if det["material"] else "No", "deterministic")

    st.subheader("What the agent did")
    step_cols = st.columns(3)
    for index, step in enumerate(payload["agent_steps"]):
        with step_cols[index % 3]:
            _render_step(st, step)

    tabs = st.tabs(["Review Summary", "Evidence Packet", "Human Approval", "Community Pattern", "Technical Proof"])

    with tabs[0]:
        left, right = st.columns(2)
        with left:
            st.markdown("### What was promised")
            st.markdown(
                f"""
                <div class="review-box">
                  <p><b>Service:</b> {case["service"]}</p>
                  <p><b>IEP text:</b> {case["iep_text"]}</p>
                  <p><b>Review window:</b> {case["window"]}</p>
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
                  <p><b>Materiality rule:</b> {det["materiality_reason"]}</p>
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
                        st.success("Draft reviewed locally. No external send occurred.")
                    else:
                        st.warning("Outbound action remains blocked.")
                elif checkpoint["resolved"]:
                    st.success("Resolved by demo policy.")
                else:
                    st.warning("Awaiting human decision.")
        st.caption("The demo never sends externally; it only shows the approval gate.")

    with tabs[3]:
        st.markdown("### District-wide pattern")
        st.caption("This is the community value: individual records can become a privacy-preserving systemic complaint.")
        systemic = payload["systemic"]
        sys_cols = st.columns(4)
        sys_cols[0].metric("Students", systemic["students_with_service"])
        sys_cols[1].metric("Material failures", systemic["students_material"])
        sys_cols[2].metric("Affected", systemic["share_material"])
        sys_cols[3].metric("Aggregate gap", systemic["aggregate_gap_label"])
        st.success(f"K-anonymous district complaint drafted with k >= {systemic['k_threshold']} and no student names.")
        with st.expander("Systemic complaint draft"):
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
        with proof_b:
            st.markdown("#### Deterministic core")
            st.write(payload["deterministic"]["materiality_reason"])
            st.write(f"Due process deadline: `{payload['deterministic']['due_process_deadline']}`")
            st.write("Grounding rejects claims without real IEP, log, and legal references.")
        draft_col, audit_col = st.columns([1.3, 1])
        with draft_col:
            st.markdown("### State complaint draft")
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
