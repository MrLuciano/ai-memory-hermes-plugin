from __future__ import annotations

import json
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

# Plugin is loaded as a standalone module (not a package) by Hermes,
# so tests import sibling modules via bare names + sys.path to match
# the production loading model exactly.
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "plugins/memory/ai-memory"),
)

from client import AiMemoryClient
from config import AiMemoryConfig
from provider import AiMemoryProvider


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read the active profile or connect to a real server in this suite."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    for key in (
        "AI_MEMORY_WORKSPACE", "AI_MEMORY_PROJECT", "AI_MEMORY_SEARCH_SCOPE",
        "AI_MEMORY_SERVER_URL", "AI_MEMORY_AUTH_TOKEN", "AI_MEMORY_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    def denied(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Real network connections are forbidden in tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def wait_for_prefetch() -> Callable[[AiMemoryProvider, str, str], None]:
    def wait(provider: AiMemoryProvider, query: str, session_id: str) -> None:
        key = provider._snapshot(session_id).cache_key(query)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with provider._lock:
                if key in provider._prefetch_cache:
                    return
            time.sleep(0.001)
        raise AssertionError(f"Prefetch cache not populated: {key}")

    return wait


@pytest.fixture
def mock_home(tmp_path: Path) -> Path:
    return tmp_path / ".hermes"


@pytest.fixture
def config() -> AiMemoryConfig:
    return AiMemoryConfig(
        server_url="http://localhost:49374",
        auth_token="test-token",
        workspace="hermes",
        project="hermes-test",
    )


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/admin/search" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    {"path": "notes/test.md", "snippet": "test content", "score": 0.95},
                ],
            )
        if "/admin/write-page" in request.url.path:
            return httpx.Response(200, json={"ok": True, "path": "notes/test.md"})
        if "/admin/status" in request.url.path:
            return httpx.Response(
                200,
                json={"ok": True, "pages": 10, "sessions": 5},
            )
        if "/hook" in request.url.path:
            return httpx.Response(200, json={"ok": True})
        if "/handoff" in request.url.path:
            # ai-memory 3.x (verified against 3.2.0) returns markdown, not JSON.
            return httpx.Response(200, text="test handoff")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_client(config: AiMemoryConfig, mock_transport: httpx.MockTransport) -> AiMemoryClient:
    client = AiMemoryClient(config)
    client._transport = mock_transport
    return client


@pytest.fixture
def provider(config: AiMemoryConfig) -> AiMemoryProvider:
    return AiMemoryProvider(config=config)


@pytest.fixture
def saved_config(mock_home: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "server_url": "http://localhost:49374",
        "auth_token": "saved-token",
        "workspace": "hermes",
        "project": "hermes-custom",
    }
    p = mock_home / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return data
