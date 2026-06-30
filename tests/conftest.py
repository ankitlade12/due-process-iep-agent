"""Test fixtures.

Force the whole suite offline regardless of any local ``.env`` key, so tests are
deterministic, fast, and never spend Qwen tokens. Live calls are exercised by the
example scripts (e.g. ``qwen_smoketest``), not by pytest.
"""

import pytest

from due_process.llm import client as _client


@pytest.fixture(autouse=True)
def force_offline(monkeypatch):
    monkeypatch.setattr(_client, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DUE_PROCESS_API_KEY", raising=False)
    _client._DEFAULT_CLIENT = None
    yield
    _client._DEFAULT_CLIENT = None
