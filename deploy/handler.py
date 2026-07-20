"""Minimal Alibaba Function Compute backend for the public hackathon proof.

The public endpoint accepts only two operations:

* ``health`` reports the deployed runtime without calling a model.
* ``synthetic-proof`` runs the repository's synthetic case through Qwen Cloud
  and the deterministic workflow, then returns provenance and aggregate facts.

It deliberately rejects custom records, storage, email, and filing actions.
No student data or outbound action belongs in this deployment-proof service.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from due_process.agent import ApprovalPolicy, run_enforcement
from due_process.instruments.drafter import LetterContext
from due_process.llm.client import LLMClient
from due_process.scenarios import worked_example_speech

BACKEND_VERSION = "1.0.0"
MAX_EVENT_BYTES = 16_384
ALLOWED_ACTIONS = {"health", "synthetic-proof"}


class SyntheticProofPolicy(ApprovalPolicy):
    """Confirm the packaged synthetic extraction, but never approve a draft."""

    name = "synthetic-proof-draft-only"

    def confirm_commitments(self, extracted):
        return True


def _decode_json(value: Any) -> dict[str, Any]:
    if value in (None, "", b""):
        return {}
    if isinstance(value, (bytes, bytearray)):
        if len(value) > MAX_EVENT_BYTES:
            raise ValueError("Request body is too large.")
        value = value.decode("utf-8")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_EVENT_BYTES:
            raise ValueError("Request body is too large.")
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("Request JSON must be an object.")
    return value


def _payload_from_event(event: Any) -> dict[str, Any]:
    """Accept direct invocations and Function Compute HTTP event envelopes."""
    outer = _decode_json(event)
    if "body" in outer:
        return _decode_json(outer.get("body"))
    if "action" in outer:
        return outer
    return {}


def _base_response(request_id: str, client: LLMClient) -> dict[str, Any]:
    return {
        "ok": True,
        "request_id": request_id,
        "service": "due-process-agent",
        "platform": "Alibaba Cloud Function Compute",
        "region": "ap-southeast-1",
        "backend_version": BACKEND_VERSION,
        "qwen_configured": _qwen_ready(client),
        "models": {
            "orchestrator": client.config.orchestrator_model,
            "workhorse": client.config.workhorse_model,
        },
        "privacy_boundary": "synthetic inputs only",
        "outbound_actions": "disabled",
    }


def _qwen_ready(client: LLMClient) -> bool:
    api_key = str(getattr(client.config, "api_key", "") or "")
    return bool(client.available and not api_key.startswith("disabled-"))


def _trace_payload(client: LLMClient) -> dict[str, Any]:
    traces = client.traces
    return {
        "successful_calls": sum(1 for item in traces if item.succeeded),
        "failed_calls": sum(1 for item in traces if not item.succeeded),
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


def _synthetic_proof(request_id: str, client: LLMClient) -> dict[str, Any]:
    if not _qwen_ready(client):
        raise RuntimeError(
            "Qwen proof is disabled until a rotated credential is deployed.")
    scenario = worked_example_speech(classified=False)
    run = run_enforcement(
        scenario.logs,
        now=datetime.now(timezone.utc),
        context=LetterContext(
            student_name="Synthetic Student",
            letter_date=date.today(),
            case_id=f"synthetic-{request_id}"[:120],
        ),
        window_start=scenario.window_start,
        window_end=scenario.window_end,
        iep_text=scenario.iep_text,
        instructional_periods=scenario.instructional_periods,
        client=client,
        policy=SyntheticProofPolicy(),
        redact=False,
        source_uri="synthetic://function-compute/worked-example",
    )
    if not run.analyses:
        raise RuntimeError("Synthetic proof did not produce an analysis.")
    analysis = run.analyses[0]
    ledger = analysis.ledger
    response = _base_response(request_id, client)
    response.update({
        "action": "synthetic-proof",
        "qwen": {
            **_trace_payload(client),
            "extraction_methods": sorted({
                item.method for item in run.extracted
            }),
            "classification_methods": sorted({
                item.method
                for item in run.classification.classifications.values()
            }) if run.classification else [],
        },
        "deterministic_result": {
            "required_minutes": ledger.required_minutes,
            "delivered_minutes": ledger.delivered_minutes,
            "unexcused_shortfall_minutes": ledger.unexcused_shortfall_minutes,
            "review_signal": analysis.materiality.is_material,
        },
        "human_control": {
            "needs_human": run.needs_human,
            "draft_statuses": [item.status.value for item in run.instruments],
            "checkpoints": [
                {
                    "kind": item.kind,
                    "resolved": item.resolved,
                    "pending": item.pending_count,
                }
                for item in run.checkpoints
            ],
        },
    })
    return response


def handler(event, context):
    """Function Compute entrypoint; always returns a JSON string."""
    request_id = str(getattr(context, "request_id", "") or uuid.uuid4())
    try:
        payload = _payload_from_event(event)
        action = str(payload.get("action", "health"))
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                "Only health and synthetic-proof actions are accepted; "
                "custom records and outbound actions are disabled."
            )
        client = LLMClient()
        if action == "health":
            response = _base_response(request_id, client)
            response["action"] = "health"
        else:
            response = _synthetic_proof(request_id, client)
        return json.dumps(response)
    except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
        return json.dumps({
            "ok": False,
            "request_id": request_id,
            "error": "invalid_request",
            "message": str(exc),
        })


if __name__ == "__main__":
    print(handler({"action": "health"}, None))
