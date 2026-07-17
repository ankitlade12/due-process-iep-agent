"""Authenticated Function Compute client for an approved OSS artifact action."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_PACKET_BYTES = 1_000_000


@dataclass(frozen=True)
class CloudActionResult:
    request_id: str
    receipt: dict[str, Any]
    audit: list[str]


class FunctionComputeArtifactClient:
    """Store the exact human-reviewed packet through Function Compute.

    The Bearer token is read server-side by Streamlit and is never placed in the
    browser payload. Function Compute independently checks both authentication
    and the explicit approval flag before invoking Alibaba OSS.
    """

    def __init__(
        self,
        *,
        function_url: str,
        api_token: str,
        timeout: int = 120,
        opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        parsed = urlparse(function_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError(
                "DUE_PROCESS_FUNCTION_URL must be a public HTTPS URL.")
        if not api_token:
            raise RuntimeError("DUE_PROCESS_API_TOKEN is not configured.")
        self.function_url = function_url
        self.api_token = api_token
        self.timeout = timeout
        self._opener = opener or urlopen

    @classmethod
    def from_env(cls) -> "FunctionComputeArtifactClient":
        return cls(
            function_url=os.environ.get("DUE_PROCESS_FUNCTION_URL", ""),
            api_token=os.environ.get("DUE_PROCESS_API_TOKEN", ""),
        )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            os.environ.get("DUE_PROCESS_FUNCTION_URL")
            and os.environ.get("DUE_PROCESS_API_TOKEN"))

    def store_approved_packet(
        self, packet: str, *, case_id: str
    ) -> CloudActionResult:
        content = packet.encode("utf-8")
        if not content:
            raise ValueError("The approved evidence packet is empty.")
        if len(content) > MAX_PACKET_BYTES:
            raise ValueError(
                f"The approved packet exceeds {MAX_PACKET_BYTES} bytes.")
        body = json.dumps({
            "action": "store_evidence_packet",
            "case_id": case_id,
            "evidence_packet": packet,
            "approval": {"store_evidence_packet": True},
        }).encode("utf-8")
        request = Request(
            self.function_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            raw = response.read()
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network boundary
            raise RuntimeError(
                "Function Compute did not return a valid artifact response.") from exc
        if not isinstance(data, dict) or not data.get("ok"):
            message = data.get("message", "Artifact storage was rejected.") \
                if isinstance(data, dict) else "Artifact storage was rejected."
            raise RuntimeError(str(message))
        receipt = data.get("artifact_receipt")
        if not isinstance(receipt, dict):
            raise RuntimeError("Function Compute returned no OSS receipt.")
        expected_hash = hashlib.sha256(content).hexdigest()
        if receipt.get("sha256") != expected_hash:
            raise RuntimeError(
                "OSS receipt hash does not match the approved packet.")
        return CloudActionResult(
            request_id=str(data.get("request_id", "")),
            receipt=receipt,
            audit=[str(item) for item in data.get("audit", [])],
        )
