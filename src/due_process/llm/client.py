"""OpenAI-compatible Qwen Cloud client and configuration.

Qwen Cloud exposes an OpenAI-compatible endpoint, so this is a thin wrapper over
the ``openai`` SDK with the base URL and key pointed at Qwen. Configuration comes
from the environment (or a local ``.env``):

  * ``DASHSCOPE_API_KEY``            — the Qwen Cloud API key
  * ``DUE_PROCESS_LLM_BASE_URL``     — override the endpoint (optional)
  * ``DUE_PROCESS_ORCHESTRATOR_MODEL`` / ``..._WORKHORSE_MODEL`` / ``..._VISION_MODEL``

Verified against docs.qwencloud.com (June 2026):
  base_url = https://dashscope-intl.aliyuncs.com/compatible-mode/v1
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# PROOF OF DEPLOYMENT — this is the Qwen Cloud (Alibaba Cloud) API base URL the
# project calls. Token Plan users override via DUE_PROCESS_LLM_BASE_URL with:
#   https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Maps the spec's intended roles onto real Qwen Cloud model ids.
DEFAULT_ORCHESTRATOR_MODEL = "qwen3.7-max"    # reasoning, drafting, the agent loop
DEFAULT_WORKHORSE_MODEL = "qwen3.6-flash"     # cheap, high-volume extraction/classify
DEFAULT_VISION_MODEL = "qwen3.7-plus"         # scanned IEP PDFs, photographed logs


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM call is attempted with no key / SDK available."""


def _load_dotenv(path: str = ".env") -> None:
    """Minimal ``.env`` loader (no dependency). Does not override real env vars."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class LLMConfig:
    """Resolved LLM configuration."""

    api_key: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    orchestrator_model: str = DEFAULT_ORCHESTRATOR_MODEL
    workhorse_model: str = DEFAULT_WORKHORSE_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    temperature: float = 0.0
    timeout: float = 60.0

    @classmethod
    def from_env(cls, load_dotenv: bool = True) -> "LLMConfig":
        if load_dotenv:
            _load_dotenv()
        return cls(
            api_key=(os.environ.get("DASHSCOPE_API_KEY")
                     or os.environ.get("DUE_PROCESS_API_KEY")),
            base_url=os.environ.get("DUE_PROCESS_LLM_BASE_URL", DEFAULT_BASE_URL),
            orchestrator_model=os.environ.get(
                "DUE_PROCESS_ORCHESTRATOR_MODEL", DEFAULT_ORCHESTRATOR_MODEL),
            workhorse_model=os.environ.get(
                "DUE_PROCESS_WORKHORSE_MODEL", DEFAULT_WORKHORSE_MODEL),
            vision_model=os.environ.get(
                "DUE_PROCESS_VISION_MODEL", DEFAULT_VISION_MODEL),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class LLMResult:
    """The text result of an LLM call, plus which model produced it."""

    text: str
    model: str
    raw: object = None


class LLMClient:
    """A thin, lazy OpenAI-compatible client for Qwen Cloud.

    The ``openai`` SDK is imported lazily so the package imports cleanly without
    it. ``available`` tells callers whether a real call is possible; task modules
    check it and fall back to their deterministic implementations when it is not.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._client = None

    @property
    def available(self) -> bool:
        return self.config.is_configured

    def _ensure(self):
        if not self.config.is_configured:
            raise LLMUnavailableError(
                "No DASHSCOPE_API_KEY configured. Set it in the environment or a "
                ".env file (see .env.example)."
            )
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise LLMUnavailableError(
                    "The 'openai' SDK is not installed. Install with "
                    "pip install 'due-process[llm]'."
                ) from exc
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def complete(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        """One chat completion. ``model`` defaults to the orchestrator model."""
        client = self._ensure()
        model = model or self.config.orchestrator_model
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=(self.config.temperature
                         if temperature is None else temperature),
            **kwargs,
        )
        return LLMResult(
            text=resp.choices[0].message.content or "",
            model=model,
            raw=resp,
        )

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
    ) -> dict:
        """Chat completion constrained to a JSON object, parsed to a dict."""
        result = self.complete(system, user, model=model, json_mode=True)
        return _parse_json_object(result.text)

    def complete_vision(
        self,
        prompt: str,
        image_b64: str,
        *,
        model: Optional[str] = None,
        mime: str = "image/png",
        system: str = "",
    ) -> LLMResult:
        """Multimodal completion over one image (for scanned IEPs / photos).

        Defaults to the vision model (qwen3.7-plus). The image is passed inline as
        a base64 data URL, per the OpenAI-compatible multimodal format.
        """
        client = self._ensure()
        model = model or self.config.vision_model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        })
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=self.config.temperature)
        return LLMResult(text=resp.choices[0].message.content or "",
                         model=model, raw=resp)


def _parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating a stray ```json fence if one slips in."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            return json.loads(text[start:end + 1])
        raise


_DEFAULT_CLIENT: Optional[LLMClient] = None


def default_client() -> LLMClient:
    """A process-wide cached client built from the environment."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = LLMClient()
    return _DEFAULT_CLIENT
