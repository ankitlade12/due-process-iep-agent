"""Function Compute boundary tests without network or cloud credentials."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def fc_handler():
    path = Path(__file__).parents[1] / "deploy" / "handler.py"
    spec = importlib.util.spec_from_file_location("fc_handler", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _custom_event(token: str = "demo-token") -> dict:
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "body": json.dumps({
            "iep_text": "Speech therapy: 1 x 30 minutes per week, individual.",
            "window_start": "2026-01-01",
            "window_end": "2026-01-31",
            "instructional_periods": 4,
            "logs": [{
                "date": "2026-01-08", "minutes_delivered": 30,
                "status": "delivered",
            }],
        }),
    }


def test_custom_case_requires_configured_auth(fc_handler, monkeypatch):
    monkeypatch.delenv("DUE_PROCESS_API_TOKEN", raising=False)
    result = json.loads(fc_handler.handler(_custom_event(), None))
    assert result["ok"] is False
    assert result["error"] == "unauthorized"


def test_custom_case_rejects_bad_token(fc_handler, monkeypatch):
    monkeypatch.setenv("DUE_PROCESS_API_TOKEN", "correct-token")
    result = json.loads(fc_handler.handler(_custom_event("wrong-token"), None))
    assert result["ok"] is False
    assert result["error"] == "unauthorized"


def test_custom_payload_bounds(fc_handler):
    payload = {
        "iep_text": "Speech therapy: 1 x 30 minutes per week.",
        "window_start": "2026-01-01",
        "window_end": "2026-01-31",
        "logs": [{"date": "2026-01-08", "minutes_delivered": 900}],
    }
    with pytest.raises(ValueError, match="0..480"):
        fc_handler._custom_inputs(payload)


def test_empty_request_is_synthetic_and_reports_real_provenance(
        fc_handler, monkeypatch):
    monkeypatch.setattr(fc_handler, "LLMClient", lambda: _OfflineClient())
    result = json.loads(fc_handler.handler(None, None))
    assert result["ok"] is True
    assert result["qwen"]["successful_calls"] == 0
    assert result["qwen"]["extraction_methods"] == ["rule_based"]
    assert result["needs_human"] is True


class _OfflineClient:
    available = False
    traces = []

    class config:
        orchestrator_model = "offline"
        workhorse_model = "offline"
