"""Hardened Alibaba Function Compute entrypoint for Due Process.

An unauthenticated empty request runs only the synthetic worked example. Custom
records require ``DUE_PROCESS_API_TOKEN`` and a matching Bearer token. Generated
packets remain drafts; an explicit approval flag is required before optional
storage in Alibaba OSS.
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from datetime import date, datetime, timezone

from due_process.agent import ApprovalPolicy, run_enforcement
from due_process.artifact_store import OSSArtifactStore
from due_process.filing import export_evidence_packet
from due_process.instruments.drafter import LetterContext
from due_process.llm.client import LLMClient
from due_process.models import LogStatus, ServiceLog
from due_process.scenarios import worked_example_speech

MAX_EVENT_BYTES = 1_000_000
MAX_IEP_CHARS = 100_000
MAX_LOG_ROWS = 2_000


class DraftOnlyPolicy(ApprovalPolicy):
    """Confirm extraction for the demo, but never approve an outbound action."""

    name = "draft-only (server)"

    def confirm_commitments(self, extracted):
        return True


def _decode_json(value) -> dict:
    if value is None or value == "":
        return {}
    if isinstance(value, (bytes, bytearray)):
        if len(value) > MAX_EVENT_BYTES:
            raise ValueError("Request body is too large.")
        value = value.decode("utf-8")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_EVENT_BYTES:
            raise ValueError("Request body is too large.")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Request JSON must be an object.")
        return parsed
    if isinstance(value, dict):
        return value
    raise ValueError("Unsupported request body type.")


def _parse_event(event) -> tuple[dict, dict]:
    outer = _decode_json(event)
    headers = {
        str(k).lower(): str(v)
        for k, v in (outer.get("headers") or {}).items()
    } if isinstance(outer.get("headers"), dict) else {}
    if "body" in outer:
        payload = _decode_json(outer.get("body"))
    else:
        payload = outer
    return payload, headers


def _require_custom_auth(headers: dict) -> None:
    expected = os.environ.get("DUE_PROCESS_API_TOKEN", "")
    if not expected:
        raise PermissionError(
            "Custom-case API is disabled until DUE_PROCESS_API_TOKEN is set.")
    supplied = headers.get("authorization", "")
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise PermissionError("A valid Bearer token is required for custom cases.")


def _logs_from_payload(rows) -> list[ServiceLog]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("logs must be a non-empty array.")
    if len(rows) > MAX_LOG_ROWS:
        raise ValueError(f"At most {MAX_LOG_ROWS} log rows are accepted.")
    logs = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"logs[{i}] must be an object.")
        try:
            row_date = date.fromisoformat(str(row["date"]))
            minutes = int(row.get("minutes_delivered", 0))
            status = LogStatus(str(row.get("status", "delivered")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"logs[{i}] has an invalid date, minutes, or status.") from exc
        if minutes < 0 or minutes > 480:
            raise ValueError(f"logs[{i}].minutes_delivered must be 0..480.")
        reason = str(row.get("missed_reason_text", ""))
        if len(reason) > 2_000:
            raise ValueError(f"logs[{i}].missed_reason_text is too long.")
        logs.append(ServiceLog(
            id=str(row.get("id", f"log-{i:03d}"))[:120],
            commitment_id=str(row.get("commitment_id", "svc-1"))[:120],
            date=row_date,
            minutes_delivered=minutes,
            status=status,
            missed_reason_text=reason,
        ))
    return logs


def _custom_inputs(payload: dict):
    iep_text = str(payload.get("iep_text", ""))
    if not iep_text.strip() or len(iep_text) > MAX_IEP_CHARS:
        raise ValueError(
            f"iep_text is required and must be at most {MAX_IEP_CHARS} characters.")
    logs = _logs_from_payload(payload.get("logs"))
    try:
        window_start = date.fromisoformat(str(payload["window_start"]))
        window_end = date.fromisoformat(str(payload["window_end"]))
        periods = int(payload.get("instructional_periods", 36))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("window_start/window_end must be ISO dates.") from exc
    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start.")
    if (window_end - window_start).days > 730:
        raise ValueError("Review windows may not exceed two years.")
    if periods < 1 or periods > 60:
        raise ValueError("instructional_periods must be between 1 and 60.")
    return logs, iep_text, window_start, window_end, periods


def _qwen_provenance(run, client, trace_start: int) -> dict:
    traces = client.traces[trace_start:]
    extraction_methods = sorted({item.method for item in run.extracted})
    classification_methods = sorted({
        item.method for item in (
            run.classification.classifications.values()
            if run.classification else [])
    })
    fallbacks = sorted({
        item.fallback_reason for item in run.extracted if item.fallback_reason
    } | {
        item.fallback_reason for item in (
            run.classification.classifications.values()
            if run.classification else []) if item.fallback_reason
    })
    return {
        "configured": client.available,
        "successful_calls": sum(1 for item in traces if item.succeeded),
        "failed_calls": sum(1 for item in traces if not item.succeeded),
        "extraction_methods": extraction_methods,
        "classification_methods": classification_methods,
        "fallbacks": fallbacks,
        "calls": [
            {
                "model": item.model,
                "operation": item.operation,
                "succeeded": item.succeeded,
                "duration_ms": item.duration_ms,
                "request_id": item.request_id,
                "error_type": item.error_type,
            }
            for item in traces
        ],
    }


def _serialize(run, client, trace_start: int, request_id: str) -> dict:
    analyses = []
    for analysis in run.analyses:
        ledger = analysis.ledger
        deadline = analysis.deadlines[0] if analysis.deadlines else None
        analyses.append({
            "service": analysis.commitment.service_type.value,
            "required_minutes": ledger.required_minutes,
            "delivered_minutes": ledger.delivered_minutes,
            "unexcused_shortfall_minutes": ledger.unexcused_shortfall_minutes,
            "shortfall_pct": float(round(ledger.shortfall_pct, 4)),
            "review_signal": analysis.materiality.is_material,
            "review_reasons": analysis.materiality.reasons,
            "compensatory_estimate_minutes": (
                analysis.compensatory.estimated_minutes
                if analysis.compensatory else 0),
            "logs_complete": ledger.logs_complete,
            "event_deadline": (
                deadline.sol_expiry_date.isoformat() if deadline else None),
            "days_remaining": deadline.days_remaining if deadline else None,
        })
    return {
        "ok": True,
        "request_id": request_id,
        "qwen": _qwen_provenance(run, client, trace_start),
        "models": {
            "orchestrator": client.config.orchestrator_model,
            "workhorse": client.config.workhorse_model,
        },
        "commitments": [c.service_type.value for c in run.commitments],
        "analyses": analyses,
        "instruments": [
            {"type": item.type.value, "status": item.status.value,
             "citations": item.citations, "draft_text": item.draft_text}
            for item in run.instruments
        ],
        "checkpoints": [
            {"kind": item.kind, "resolved": item.resolved,
             "pending": item.pending_count} for item in run.checkpoints
        ],
        "audit": run.audit_lines(),
        "needs_human": run.needs_human,
    }


def handler(event, context):
    """Function Compute entrypoint; always returns a JSON string."""
    request_id = str(getattr(context, "request_id", "") or uuid.uuid4())
    try:
        payload, headers = _parse_event(event)
        custom_case = bool(payload.get("logs") or payload.get("iep_text"))
        if custom_case:
            _require_custom_auth(headers)
            logs, iep_text, window_start, window_end, periods = _custom_inputs(payload)
        else:
            scenario = worked_example_speech(classified=False)
            logs, iep_text = scenario.logs, scenario.iep_text
            window_start, window_end = scenario.window_start, scenario.window_end
            periods = scenario.instructional_periods

        # Per-request client keeps trace provenance isolated when Function
        # Compute handles concurrent warm invocations.
        client = LLMClient()
        trace_start = len(client.traces)
        run = run_enforcement(
            logs,
            now=datetime.now(timezone.utc),
            context=LetterContext(
                student_name="[Redacted Student]", letter_date=date.today(),
                case_id=str(payload.get("case_id", request_id))[:120]),
            window_start=window_start,
            window_end=window_end,
            iep_text=iep_text,
            instructional_periods=periods,
            client=client,
            policy=DraftOnlyPolicy(),
        )
        response = _serialize(run, client, trace_start, request_id)

        approval = payload.get("approval") or {}
        if approval.get("store_evidence_packet") is True:
            if not custom_case:
                raise ValueError("Synthetic demo artifacts are not stored.")
            if not run.instruments:
                raise ValueError("No draft evidence packet is available to store.")
            packet = export_evidence_packet(run.instruments[0], run.analyses)
            receipt = OSSArtifactStore.from_env().put_evidence_packet(
                packet, case_id=str(payload.get("case_id", request_id)))
            response["artifact_receipt"] = receipt.to_dict()
            response["audit"].append(
                f"[external_tool] Human-approved packet stored at {receipt.uri} "
                f"sha256={receipt.sha256}.")
        return json.dumps(response)
    except PermissionError as exc:
        return json.dumps({"ok": False, "request_id": request_id,
                           "error": "unauthorized", "message": str(exc)})
    except (ValueError, RuntimeError) as exc:
        return json.dumps({"ok": False, "request_id": request_id,
                           "error": "invalid_request", "message": str(exc)})


if __name__ == "__main__":
    print(handler(None, None))
