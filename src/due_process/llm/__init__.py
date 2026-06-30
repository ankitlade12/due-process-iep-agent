"""The bounded LLM layer.

Every task here is *bounded*: the LLM fills a fixed scaffold and never does math
or law lookup. Each task ships two implementations behind one interface:

  * a transparent, deterministic fallback (keyword rules / regex / templates)
    that runs offline with no API key, and
  * a Qwen-backed implementation (via :class:`due_process.llm.client.LLMClient`,
    the OpenAI-compatible Qwen Cloud endpoint) used when a key is configured.

This keeps the whole system runnable and testable with no credentials, and lets
it upgrade to Qwen for messy real-world inputs the moment ``DASHSCOPE_API_KEY``
is present.
"""

from .client import LLMClient, LLMConfig, LLMResult, LLMUnavailableError, default_client

__all__ = [
    "LLMClient",
    "LLMConfig",
    "LLMResult",
    "LLMUnavailableError",
    "default_client",
]
