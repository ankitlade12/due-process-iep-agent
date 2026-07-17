"""Tests for the Streamlit-to-Function-Compute approval action."""

import hashlib
import json

import pytest

from due_process.cloud_action import FunctionComputeArtifactClient


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_cloud_action_sends_exact_packet_and_verifies_receipt():
    packet = "approved evidence packet"
    digest = hashlib.sha256(packet.encode("utf-8")).hexdigest()
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({
            "ok": True,
            "request_id": "fc-request-1",
            "artifact_receipt": {
                "provider": "alibaba-oss",
                "uri": "oss://private/evidence-packets/case/hash.txt",
                "sha256": digest,
                "size_bytes": len(packet),
                "stored_at": "2026-07-17T12:00:00Z",
            },
            "audit": ["[external_tool] stored"],
        })

    client = FunctionComputeArtifactClient(
        function_url="https://example.fc.aliyuncs.com/invoke",
        api_token="server-side-token",
        opener=opener,
    )
    result = client.store_approved_packet(packet, case_id="case-1")

    sent = json.loads(captured["request"].data.decode("utf-8"))
    assert sent["evidence_packet"] == packet
    assert sent["approval"]["store_evidence_packet"] is True
    assert captured["request"].headers["Authorization"] == (
        "Bearer server-side-token")
    assert result.receipt["sha256"] == digest
    assert result.request_id == "fc-request-1"


def test_cloud_action_rejects_mismatched_receipt_hash():
    client = FunctionComputeArtifactClient(
        function_url="https://example.fc.aliyuncs.com/invoke",
        api_token="token",
        opener=lambda request, timeout: _Response({
            "ok": True,
            "artifact_receipt": {"sha256": "wrong"},
        }),
    )
    with pytest.raises(RuntimeError, match="hash does not match"):
        client.store_approved_packet("approved packet", case_id="case-1")


def test_cloud_action_requires_https():
    with pytest.raises(RuntimeError, match="HTTPS"):
        FunctionComputeArtifactClient(
            function_url="http://example.test", api_token="token")
