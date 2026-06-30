"""Alibaba Cloud Function Compute handler — the proof-of-deployment artifact.

This is the code file that demonstrates Alibaba Cloud API usage: when invoked it
runs the Due Process enforcement agent, which calls **Qwen Cloud Model Studio**
(the Alibaba Cloud OpenAI-compatible endpoint) for extraction, classification,
and the letter narrative, while the deterministic core does all the math and law.

Deploy with Serverless Devs (`s deploy`) using the sibling ``s.yaml``; invoke with
a JSON payload, or with no payload to run the built-in worked example.

Event payload (all optional; omit to use the worked example):
    {
      "iep_text": "Speech-Language Therapy: 3 x 30 minutes per week, individual.",
      "instructional_periods": 36,
      "window_start": "2025-09-02",
      "window_end": "2026-05-09",
      "logs": [
        {"date": "2025-09-04", "minutes_delivered": 0, "status": "missed",
         "missed_reason_text": "Provider absent, no substitute"}
      ]
    }

The function drafts instruments but never auto-sends them — sending stays a human
decision, consistent with the Track 4 human-in-the-loop design.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from due_process.agent import ApprovalPolicy, run_enforcement
from due_process.instruments.drafter import LetterContext
from due_process.llm.client import default_client
from due_process.models import LogStatus, ServiceLog
from due_process.scenarios import worked_example_speech


class DraftOnlyPolicy(ApprovalPolicy):
    """Confirms parsed commitments so analysis runs, but never auto-sends.

    A stateless function prepares the remedy; a human still approves the send.
    """

    name = "draft-only (server)"

    def confirm_commitments(self, extracted):
        return True


def _logs_from_payload(rows):
    logs = []
    for i, row in enumerate(rows):
        logs.append(ServiceLog(
            id=row.get("id", f"log-{i:03d}"),
            commitment_id=row.get("commitment_id", "svc-1"),
            date=date.fromisoformat(row["date"]),
            minutes_delivered=int(row.get("minutes_delivered", 0)),
            status=LogStatus(row.get("status", "delivered")),
            missed_reason_text=row.get("missed_reason_text", ""),
        ))
    return logs


def _parse_event(event) -> dict:
    if event is None:
        return {}
    if isinstance(event, (bytes, bytearray)):
        event = event.decode("utf-8")
    if isinstance(event, str):
        event = event.strip()
        if not event:
            return {}
        try:
            return json.loads(event)
        except json.JSONDecodeError:
            return {}
    return event if isinstance(event, dict) else {}


def _serialize(run, client) -> dict:
    analyses = []
    for a in run.analyses:
        led = a.ledger
        deadline = a.deadlines[0] if a.deadlines else None
        analyses.append({
            "service": a.commitment.service_type.value,
            "required_minutes": led.required_minutes,
            "delivered_minutes": led.delivered_minutes,
            "unexcused_shortfall_minutes": led.unexcused_shortfall_minutes,
            "shortfall_pct": float(round(led.shortfall_pct, 4)),
            "material_failure": a.materiality.is_material,
            "compensatory_minutes": (a.compensatory.estimated_minutes
                                     if a.compensatory else 0),
            "logs_complete": led.logs_complete,
            "deadline": (deadline.sol_expiry_date.isoformat()
                         if deadline else None),
            "days_remaining": deadline.days_remaining if deadline else None,
        })
    return {
        "llm": "qwen-online" if client.available else "offline-fallback",
        "models": {
            "orchestrator": client.config.orchestrator_model,
            "workhorse": client.config.workhorse_model,
        },
        "commitments": [c.service_type.value for c in run.commitments],
        "analyses": analyses,
        "instruments": [
            {"type": i.type.value, "status": i.status.value,
             "citations": i.citations, "draft_text": i.draft_text}
            for i in run.instruments
        ],
        "checkpoints": [
            {"kind": c.kind, "resolved": c.resolved,
             "pending": c.pending_count} for c in run.checkpoints
        ],
        "audit": run.audit_lines(),
        "needs_human": run.needs_human,
    }


def handler(event, context):
    """Function Compute entrypoint."""
    payload = _parse_event(event)
    client = default_client()

    if payload.get("logs"):
        logs = _logs_from_payload(payload["logs"])
        iep_text = payload.get("iep_text", "")
        window_start = date.fromisoformat(payload["window_start"])
        window_end = date.fromisoformat(payload["window_end"])
        periods = int(payload.get("instructional_periods", 36))
    else:
        scenario = worked_example_speech(classified=False)
        logs = scenario.logs
        iep_text = scenario.iep_text
        window_start = scenario.window_start
        window_end = scenario.window_end
        periods = scenario.instructional_periods

    run = run_enforcement(
        logs,
        now=datetime.now(timezone.utc),
        context=LetterContext(student_name="[Student]", letter_date=date.today()),
        window_start=window_start,
        window_end=window_end,
        iep_text=iep_text,
        instructional_periods=periods,
        client=client,
        policy=DraftOnlyPolicy(),
    )
    return json.dumps(_serialize(run, client))


if __name__ == "__main__":
    # Local smoke test of the handler (no Function Compute needed).
    print(handler(None, None))
