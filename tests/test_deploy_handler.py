"""Boundary tests for the synthetic-only Function Compute backend."""

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


class _OfflineClient:
    available = False
    traces = []

    class config:
        api_key = ""
        orchestrator_model = "offline"
        workhorse_model = "offline"


class _ConfiguredFallbackClient(_OfflineClient):
    available = True

    class config:
        api_key = "test-only-key"
        orchestrator_model = "test-orchestrator"
        workhorse_model = "test-workhorse"

    def complete_json(self, *_args, **_kwargs):
        raise RuntimeError("offline test")

    def complete(self, *_args, **_kwargs):
        raise RuntimeError("offline test")


def test_health_reports_alibaba_runtime_without_model_call(
        fc_handler, monkeypatch):
    monkeypatch.setattr(fc_handler, "LLMClient", lambda: _OfflineClient())

    result = json.loads(fc_handler.handler({"action": "health"}, None))

    assert result["ok"] is True
    assert result["platform"] == "Alibaba Cloud Function Compute"
    assert result["action"] == "health"
    assert result["outbound_actions"] == "disabled"
    assert "qwen" not in result


def test_synthetic_proof_requires_a_real_qwen_credential(
        fc_handler, monkeypatch):
    monkeypatch.setattr(fc_handler, "LLMClient", lambda: _OfflineClient())

    result = json.loads(fc_handler.handler(
        {"action": "synthetic-proof"}, None))

    assert result["ok"] is False
    assert result["error"] == "invalid_request"
    assert "rotated credential" in result["message"]


def test_synthetic_proof_runs_same_deterministic_and_human_boundaries(
        fc_handler, monkeypatch):
    monkeypatch.setattr(
        fc_handler, "LLMClient", lambda: _ConfiguredFallbackClient())

    result = json.loads(fc_handler.handler(
        {"action": "synthetic-proof"}, None))

    assert result["ok"] is True
    assert result["qwen"]["successful_calls"] == 0
    assert result["qwen"]["extraction_methods"] == ["rule_based"]
    assert result["deterministic_result"]["required_minutes"] == 3240
    assert result["deterministic_result"]["unexcused_shortfall_minutes"] == 720
    assert result["human_control"]["needs_human"] is True
    assert result["human_control"]["draft_statuses"] == ["draft"]


@pytest.mark.parametrize("action", ["custom-case", "store", "email", "file"])
def test_backend_rejects_custom_and_outbound_actions(
        fc_handler, monkeypatch, action):
    monkeypatch.setattr(fc_handler, "LLMClient", lambda: _OfflineClient())

    result = json.loads(fc_handler.handler({"action": action}, None))

    assert result["ok"] is False
    assert result["error"] == "invalid_request"
    assert "disabled" in result["message"]


def test_http_event_envelope_is_supported(fc_handler, monkeypatch):
    monkeypatch.setattr(fc_handler, "LLMClient", lambda: _OfflineClient())
    event = {"body": json.dumps({"action": "health"})}

    result = json.loads(fc_handler.handler(event, None))

    assert result["ok"] is True
    assert result["action"] == "health"
