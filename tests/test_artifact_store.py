"""Tests for the approval-gated Alibaba OSS artifact adapter."""

import due_process.artifact_store as artifact_store

from due_process.artifact_store import OSSArtifactStore


class _Result:
    status = 200


class _Bucket:
    def __init__(self):
        self.calls = []

    def put_object(self, key, content, headers=None):
        self.calls.append((key, content, headers))
        return _Result()


def test_oss_receipt_is_content_addressed():
    bucket = _Bucket()
    store = OSSArtifactStore(
        bucket_name="demo", endpoint="oss.example",
        access_key_id="test", access_key_secret="test", bucket=bucket)
    receipt = store.put_evidence_packet("evidence", case_id="Case 42")

    assert receipt.provider == "alibaba-oss"
    assert receipt.uri.startswith("oss://demo/evidence-packets/Case-42/")
    assert receipt.size_bytes == len(b"evidence")
    assert len(receipt.sha256) == 64
    assert bucket.calls[0][2]["Content-Type"].startswith("text/plain")


def test_stdlib_oss_client_builds_signed_https_put(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Result()

    monkeypatch.setattr(artifact_store, "urlopen", fake_urlopen)
    store = OSSArtifactStore(
        bucket_name="due-process-private",
        endpoint="https://oss-ap-southeast-1.aliyuncs.com",
        access_key_id="limited-id",
        access_key_secret="limited-secret",
    )
    receipt = store.put_evidence_packet(
        "safe synthetic packet", case_id="case 1")

    request = captured["request"]
    assert request.full_url.startswith(
        "https://due-process-private.oss-ap-southeast-1.aliyuncs.com/")
    assert request.get_method() == "PUT"
    assert request.headers["Authorization"].startswith("OSS limited-id:")
    assert captured["timeout"] == 30
    assert receipt.uri.startswith("oss://due-process-private/")
