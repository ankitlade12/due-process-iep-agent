"""Approval-gated external storage for generated evidence packets."""

from __future__ import annotations

import hashlib
import base64
import hmac
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any, Optional
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ArtifactReceipt:
    provider: str
    uri: str
    sha256: str
    size_bytes: int
    stored_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_key_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned[:80] or "case"


class OSSArtifactStore:
    """Minimal Alibaba OSS adapter invoked only after human approval."""

    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint: str,
        access_key_id: str,
        access_key_secret: str,
        bucket: Optional[Any] = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        if bucket is not None:
            self.bucket = bucket
            return
        self.bucket = _OSSRestBucket(
            bucket_name=bucket_name,
            endpoint=endpoint,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )

    @classmethod
    def from_env(cls) -> "OSSArtifactStore":
        # Use a separate, least-privilege OSS identity in production. Falling
        # back to the deployment identity keeps local setup backwards-compatible.
        required = {
            "bucket_name": os.environ.get("DUE_PROCESS_OSS_BUCKET", ""),
            "endpoint": os.environ.get("DUE_PROCESS_OSS_ENDPOINT", ""),
            "access_key_id": (
                os.environ.get("DUE_PROCESS_OSS_ACCESS_KEY_ID", "")
                or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
            ),
            "access_key_secret": (
                os.environ.get("DUE_PROCESS_OSS_ACCESS_KEY_SECRET", "")
                or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
            ),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "OSS storage is not configured; missing: " + ", ".join(missing))
        return cls(**required)

    def put_evidence_packet(self, packet: str, *, case_id: str) -> ArtifactReceipt:
        content = packet.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        key = f"evidence-packets/{_safe_key_part(case_id)}/{digest[:16]}.txt"
        result = self.bucket.put_object(
            key, content,
            headers={"Content-Type": "text/plain; charset=utf-8"})
        status = int(getattr(result, "status", 200))
        if status < 200 or status >= 300:
            raise RuntimeError(f"OSS rejected the evidence packet (HTTP {status}).")
        return ArtifactReceipt(
            provider="alibaba-oss",
            uri=f"oss://{self.bucket_name}/{key}",
            sha256=digest,
            size_bytes=len(content),
            stored_at=datetime.now(timezone.utc).isoformat(),
        )


class _OSSRestBucket:
    """Minimal OSS Signature V1 PUT client using only Python's stdlib.

    Function Compute's deployment bundle therefore needs no platform-specific
    OSS SDK wheels. The injected ``bucket`` seam above keeps this boundary easy
    to test without network calls.
    """

    _BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")

    def __init__(self, *, bucket_name: str, endpoint: str,
                 access_key_id: str, access_key_secret: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise RuntimeError("DUE_PROCESS_OSS_ENDPOINT must be an HTTPS origin.")
        if not self._BUCKET_RE.fullmatch(bucket_name):
            raise RuntimeError("DUE_PROCESS_OSS_BUCKET is not a valid OSS bucket name.")
        self.bucket_name = bucket_name
        self.endpoint_host = parsed.netloc
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret

    def put_object(self, key: str, content: bytes, *, headers: dict[str, str]):
        content_type = headers.get("Content-Type", "application/octet-stream")
        now = datetime.now(timezone.utc)
        date_header = format_datetime(now, usegmt=True)
        canonical_resource = f"/{self.bucket_name}/{key}"
        string_to_sign = (
            f"PUT\n\n{content_type}\n{date_header}\n{canonical_resource}")
        signature = base64.b64encode(hmac.new(
            self.access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"), hashlib.sha1,
        ).digest()).decode("ascii")
        url = (
            f"https://{self.bucket_name}.{self.endpoint_host}/"
            f"{quote(key, safe='/')}")
        request = Request(url, data=content, method="PUT", headers={
            "Content-Type": content_type,
            "Date": date_header,
            "Authorization": f"OSS {self.access_key_id}:{signature}",
        })
        try:
            return urlopen(request, timeout=30)  # noqa: S310 - trusted HTTPS endpoint
        except Exception as exc:  # pragma: no cover - cloud boundary
            raise RuntimeError("Alibaba OSS upload failed.") from exc
