from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from client import SESSION_END_TIMEOUT
from config import AiMemoryConfig
from provider import AiMemoryProvider


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> AiMemoryProvider:
    cfg = AiMemoryConfig(
        server_url="http://localhost:49374",
        auth_token="test-token",
        workspace="hermes",
        project="hermes-test",
    )
    p = AiMemoryProvider(config=cfg)
    # initialize() now fetches a handoff; keep unit tests off the
    # network (a real ai-memory may well be listening on :49374).
    p._client = MagicMock()
    p._client.fetch_handoff.return_value = None
    monkeypatch.setattr("provider.AiMemoryClient", lambda *args, **kwargs: p._client)
    return p


def test_provider_name(provider: AiMemoryProvider) -> None:
    assert provider.name == "ai-memory"


def test_is_available_with_token(provider: AiMemoryProvider) -> None:
    assert provider.is_available() is True


def test_is_available_without_token() -> None:
    # ai-memory is available without auth tokens — only server_url matters.
    p = AiMemoryProvider(config=AiMemoryConfig())
    assert p.is_available() is True


def test_is_available_without_server_url() -> None:
    p = AiMemoryProvider(config=AiMemoryConfig(server_url=""))
    assert p.is_available() is False


def test_initialize_sets_session_id(provider: AiMemoryProvider) -> None:
    provider.initialize("session-123", agent_identity="test-profile")
    assert provider.session_id == "session-123"
    # A project configured in ai-memory.json is no longer clobbered.
    assert provider._config.project == "hermes-test"


def test_get_config_schema(provider: AiMemoryProvider) -> None:
    schema = provider.get_config_schema()
    assert len(schema) >= 4


def test_save_config(tmp_path: Path, provider: AiMemoryProvider) -> None:
    hermes_home = str(tmp_path)
    provider.save_config({"server_url": "http://custom:49374"}, hermes_home)
    p = tmp_path / "ai-memory.json"
    assert p.exists()


def test_get_tool_schemas(provider: AiMemoryProvider) -> None:
    schemas = provider.get_tool_schemas()
    names = [s["name"] for s in schemas]
    assert "ai_memory_search" in names
    assert "ai_memory_write" in names
    assert "ai_memory_status" in names


def test_handle_tool_call_search(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(return_value=[{"path": "test.md"}])
    result = json.loads(provider.handle_tool_call("ai_memory_search", {"query": "test"}))
    assert result["ok"] is True
    assert len(result["results"]) == 1


def test_search_defaults_invalid_max_results(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(return_value=[])
    provider._search({"query": "test", "max_results": "invalid"})
    assert provider._client.search.call_args.kwargs["limit"] == 5


def test_handle_tool_call_write(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock(return_value={"ok": True})
    result = json.loads(
        provider.handle_tool_call(
            "ai_memory_write",
            {"path": "notes/test.md", "body": "# Hello"},
        )
    )
    assert result["ok"] is True
    assert result["written"] == "notes/test.md"


def test_handle_tool_call_write_accepts_current_api_page_id(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock(return_value={"page_id": "page-123"})
    result = json.loads(
        provider.handle_tool_call(
            "ai_memory_write",
            {"path": "notes/test.md", "body": "# Hello"},
        )
    )
    assert result == {"ok": True, "written": "notes/test.md"}


def test_handle_tool_call_status(provider: AiMemoryProvider) -> None:
    provider._client.status = MagicMock(return_value={"ok": True, "pages": 10})
    result = json.loads(provider.handle_tool_call("ai_memory_status", {}))
    assert result["ok"] is True


def test_handle_tool_call_returns_json_string(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(return_value=[])
    result = provider.handle_tool_call("ai_memory_search", {"query": "test"})
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "ok" in parsed


def test_handle_tool_call_unknown(provider: AiMemoryProvider) -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        provider.handle_tool_call("unknown_tool", {})


def test_system_prompt_block(provider: AiMemoryProvider) -> None:
    block = provider.system_prompt_block()
    assert "ai-memory" in block


def test_prefetch_returns_context(provider: AiMemoryProvider) -> None:
    provider._search = MagicMock(
        return_value={
            "ok": True,
            "results": [
                {"snippet": "context 1"},
                {"snippet": "context 2"},
            ],
        }
    )
    result = provider.prefetch("test query")
    assert result is not None
    assert "context 1" in result
    assert "context 2" in result


def test_prefetch_returns_empty_on_no_results(provider: AiMemoryProvider) -> None:
    provider._search = MagicMock(return_value={"ok": True, "results": []})
    result = provider.prefetch("test query")
    assert result == ""


def test_sync_turn_spawns_daemon(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.sync_turn("user msg", "assistant msg", session_id="sess-1")
    time.sleep(0.05)
    provider._client.send_hook.assert_called_once()


def test_sync_turn_absorbs_extra_kwargs(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.sync_turn(
        "user msg", "assistant msg", session_id="sess-1", context="extra", extra_key="val"
    )
    time.sleep(0.05)
    provider._client.send_hook.assert_called_once()


def test_on_session_end_spawns_daemon(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.on_session_end([{"role": "user", "content": "hello"}])
    time.sleep(0.05)
    provider._client.send_hook.assert_called_once()


def test_on_session_end_absorbs_extra_kwargs(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.on_session_end([{"role": "user", "content": "hello"}], extra_key="val")
    time.sleep(0.05)
    provider._client.send_hook.assert_called_once()


def test_on_memory_write_calls_client(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("write", "notes/foo", "# content")
    provider.shutdown()  # join the background mirror
    provider._client.write_page.assert_called_once()


def test_on_memory_write_with_metadata(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("write", "notes/foo", "# content", metadata={"tags": ["test"]})
    provider.shutdown()
    provider._client.write_page.assert_called_once()


def test_on_memory_write_skips_other_actions(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("delete", "notes/foo", "# content")
    provider._client.write_page.assert_not_called()


def test_queue_prefetch_fills_the_next_prefetch(
    provider: AiMemoryProvider,
    wait_for_prefetch: Callable[[AiMemoryProvider, str, str], None],
) -> None:
    """Hermes calls ``queue_prefetch(query, session_id=...)`` after each turn.

    Regression: the old signature took only ``query``, so the manager's
    keyword call raised TypeError, the error was swallowed as "non-fatal", and
    the background recall never ran.
    """
    provider._client.search = MagicMock(
        return_value=[{"path": "concepts/x.md", "title": "X", "snippet": "cached body"}]
    )
    provider.queue_prefetch("test query", session_id="sess-9")
    wait_for_prefetch(provider, "test query", "sess-9")
    provider._client.search.assert_called_once_with(query="test query", limit=3)

    provider._search = MagicMock(side_effect=AssertionError("cache miss"))
    result = provider.prefetch("test query", session_id="sess-9")
    assert "cached body" in result
    provider._search.assert_not_called()


def test_prefetch_is_not_shared_between_sessions(
    provider: AiMemoryProvider,
    wait_for_prefetch: Callable[[AiMemoryProvider, str, str], None],
) -> None:
    """Results are cached per ``(session_id, query)``, never across sessions."""
    provider._client.search = MagicMock(return_value=[{"snippet": "sess-9 body"}])
    provider.queue_prefetch("same query", session_id="sess-9")
    wait_for_prefetch(provider, "same query", "sess-9")
    provider._search = MagicMock(return_value={"ok": True, "results": [{"snippet": "sess-1 body"}]})
    assert "sess-1 body" in provider.prefetch("same query", session_id="sess-1")
    provider._search.assert_called_once()


def test_prefetch_labels_hits_with_path_and_title(provider: AiMemoryProvider) -> None:
    """Recall is global, so each injected hit names the page it came from."""
    provider._search = MagicMock(
        return_value={
            "ok": True,
            "results": [{"path": "conceitos/x.md", "title": "X", "snippet": "corpo"}],
        }
    )
    result = provider.prefetch("test query")
    assert "X (conceitos/x.md)" in result
    assert "corpo" in result


def test_recall_status_reflects_last_prefetch(provider: AiMemoryProvider) -> None:
    provider._search = MagicMock(
        return_value={"ok": True, "results": [{"snippet": "a"}, {"snippet": "b"}]}
    )
    provider.prefetch("test query")
    status = provider.recall_status()
    assert status is not None
    assert status.provider_label == "ai-memory"
    assert status.count == 2

    provider._search = MagicMock(return_value={"ok": True, "results": []})
    provider.prefetch("test query")
    assert provider.recall_status() is None


def test_tool_schemas_use_parameters_key(provider: AiMemoryProvider) -> None:
    """Hermes normalizes ``parameters``; an ``input_schema`` schema reaches the
    request with no argument list at all."""
    schemas = provider.get_tool_schemas()
    assert schemas
    for schema in schemas:
        assert "parameters" in schema, schema["name"]
        assert "input_schema" not in schema


def test_search_schema_declares_its_required_argument(provider: AiMemoryProvider) -> None:
    schema = next(s for s in provider.get_tool_schemas() if s["name"] == "ai_memory_search")
    assert schema["parameters"]["required"] == ["query"]
    assert "query" in schema["parameters"]["properties"]


def test_on_memory_write_mirrors_add(provider: AiMemoryProvider) -> None:
    """Hermes announces built-in writes as add|replace|remove."""
    provider._client.write_page = MagicMock()
    provider.on_memory_write("add", "memory", "# entry")
    provider.shutdown()
    kwargs = provider._client.write_page.call_args.kwargs
    assert kwargs["path"] == "hermes-memory/memory.md"
    assert kwargs["body"] == "# entry"
    assert kwargs["tags"] == ["hermes", "mirror"]


def test_on_memory_write_replace_keeps_previous_content(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("replace", "user", "# novo", metadata={"previous_content": "# antigo"})
    provider.shutdown()
    assert provider._client.write_page.call_args.kwargs["path"] == "hermes-memory/user.md"
    body = provider._client.write_page.call_args.kwargs["body"]
    assert "# novo" in body
    assert "# antigo" in body


def test_on_memory_write_skips_remove(provider: AiMemoryProvider) -> None:
    """The mirror keeps page history; a delete gets no tombstone."""
    provider._client.write_page = MagicMock()
    provider.on_memory_write("remove", "memory", "# entry", metadata={"old_text": "# entry"})
    provider._client.write_page.assert_not_called()


def test_unavailable_reason_when_server_url_missing() -> None:
    p = AiMemoryProvider(config=AiMemoryConfig(server_url=""))
    assert "AI_MEMORY_SERVER_URL" in p.unavailable_reason()


def test_unavailable_reason_is_empty_when_healthy() -> None:
    p = AiMemoryProvider(config=AiMemoryConfig())
    assert p.unavailable_reason() == ""


def test_initialize_resolves_workspace_from_kwargs(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="test-profile", ai_memory_workspace="ws-custom")
    assert provider._config.workspace == "ws-custom"


def test_initialize_project_kwarg_overrides_profile(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="test-profile", project="custom-proj")
    assert provider._config.project == "custom-proj"


def test_initialize_passes_session_cwd_to_handoff(
    provider: AiMemoryProvider, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    provider.initialize(
        "sess-1",
        cwd=str(repo),
        profile="test-profile",
        ai_memory_workspace="ws-custom",
        project="custom-proj",
    )
    provider._client.fetch_handoff.assert_called_once_with(
        agent="hermes",
        cwd=str(repo),
        workspace="ws-custom",
        project="custom-proj",
    )


def test_initialize_preserves_default_workspace(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", agent_identity="test-profile")
    assert provider._config.workspace == "hermes"


def test_initialize_uses_identity_when_no_configured_project(
    provider: AiMemoryProvider,
) -> None:
    provider._config.project = ""
    provider.initialize("sess-1", agent_identity="custom-profile")
    assert provider._config.project == "hermes-custom-profile"


def test_prefetch_propagates_search_errors(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(side_effect=RuntimeError("search failed"))
    with pytest.raises(RuntimeError, match="search failed"):
        provider.prefetch("test query")


def test_handle_tool_call_propagates_errors(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(side_effect=RuntimeError("search failed"))
    with pytest.raises(RuntimeError):
        provider.handle_tool_call("ai_memory_search", {"query": "test"})


# ------------------------------------------------- background worker lifecycle
def test_background_work_uses_spawn_context_thread_when_importable(
    provider: AiMemoryProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hermes requires provider threads to inherit the caller's contextvars."""
    spawned: list[str] = []

    def spawn(target: Callable[[], None], *, name: str, daemon: bool = True) -> threading.Thread:
        spawned.append(name)
        return threading.Thread(target=target, name=name, daemon=daemon)

    agent_module = ModuleType("agent")
    agent_module.__path__ = []
    provider_module = ModuleType("agent.memory_provider")
    setattr(provider_module, "spawn_context_thread", spawn)
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.memory_provider", provider_module)

    provider._client.send_hook = MagicMock()
    provider._client.write_page = MagicMock()
    provider.sync_turn("user", "assistant")
    provider.on_session_end([])
    provider.on_memory_write("add", "memory", "# entry")
    provider.shutdown()

    assert spawned == [
        "ai-memory-sync-turn",
        "ai-memory-session-end",
        "ai-memory-memory-write",
    ]


def test_background_work_falls_back_to_a_daemon_thread_without_hermes(
    provider: AiMemoryProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plugin must still load and work standalone (no ``agent`` package)."""
    created: list[Any] = []

    class FallbackThread:
        def __init__(self, *, target: Callable[[], None], name: str, daemon: bool) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            created.append(self)

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return False

    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setattr("provider.threading.Thread", FallbackThread)
    provider.sync_turn("user", "assistant")

    assert len(created) == 1
    assert created[0].name == "ai-memory-sync-turn"
    assert created[0].daemon is True
    assert created[0].started is True


def test_shutdown_waits_out_a_session_end_worker_budget(
    provider: AiMemoryProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session-end POST gets the client's 10s budget, not the generic 5s slice.

    Shutdown must still be bounded; the fake join returns immediately, so only
    the timeout it was handed is under test.
    """
    joins: list[float | None] = []

    class TrackedThread:
        def __init__(self, *, target: Callable[[], None], name: str, daemon: bool) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            joins.append(timeout)

    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setattr("provider.threading.Thread", TrackedThread)
    provider.on_session_end([{"role": "user", "content": "hello"}])
    provider.shutdown()

    assert len(joins) == 1
    assert joins[0] is not None
    # The old shared 5s deadline abandoned a session-end POST still in flight.
    assert joins[0] > 5.0
    assert joins[0] <= SESSION_END_TIMEOUT


def test_shutdown_joins_a_tracked_but_unstarted_worker(
    provider: AiMemoryProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tracked thread reporting is_alive() == False must not be skipped.

    That is exactly what a created-but-not-yet-started thread returns, so the
    old snapshot-then-skip logic let such a worker start after shutdown.
    """
    joins: list[float | None] = []

    class UnstartedThread:
        def __init__(self, *, target: Callable[[], None], name: str, daemon: bool) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            joins.append(timeout)

    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setattr("provider.threading.Thread", UnstartedThread)
    provider.sync_turn("user", "assistant")
    provider.shutdown()

    assert len(joins) == 1
    assert joins[0] is not None


def test_spawn_after_shutdown_runs_inline_and_creates_no_thread(
    provider: AiMemoryProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spawn racing in after shutdown began must not leak an untracked thread."""
    provider.shutdown()

    class ExplodingThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("shutdown already began; no thread may be created")

    provider._client.write_page = MagicMock()
    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setattr("provider.threading.Thread", ExplodingThread)
    provider.on_memory_write("add", "memory", "# late entry")

    provider._client.write_page.assert_called_once()
    assert provider._worker_threads == []


def test_on_memory_write_does_not_block_on_a_slow_client(provider: AiMemoryProvider) -> None:
    """Hermes calls this inline in the tool loop; a 10s write would stall the turn."""
    started = threading.Event()
    release = threading.Event()

    def slow_write(**kwargs: Any) -> dict[str, Any]:
        started.set()
        release.wait(2)
        return {"ok": True}

    provider._client.write_page = MagicMock(side_effect=slow_write)
    began = time.monotonic()
    provider.on_memory_write("add", "memory", "# entry")
    elapsed = time.monotonic() - began

    assert elapsed < 0.5
    assert started.wait(1)
    release.set()
    provider.shutdown()
    provider._client.write_page.assert_called_once()


# ------------------------------------------------------------ prefetch cache
def test_next_turn_consumes_queued_recall_even_when_its_query_differs(
    provider: AiMemoryProvider,
    wait_for_prefetch: Callable[[AiMemoryProvider, str, str], None],
) -> None:
    """Hermes queues with the completed turn's text but prefetches with the next
    turn's text, so the exact-query key alone can never be the mechanism."""
    provider._client.search = MagicMock(return_value=[{"snippet": "queued body"}])
    provider.queue_prefetch("the first turn", session_id="sess-9")
    wait_for_prefetch(provider, "the first turn", "sess-9")

    provider._search = MagicMock(side_effect=AssertionError("cache miss"))
    result = provider.prefetch("a different second turn", session_id="sess-9")
    assert "queued body" in result
    provider._search.assert_not_called()
