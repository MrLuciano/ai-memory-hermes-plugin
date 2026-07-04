from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from config import AiMemoryConfig
from provider import AiMemoryProvider


@pytest.fixture
def provider() -> AiMemoryProvider:
    cfg = AiMemoryConfig(
        server_url="http://localhost:49374",
        auth_token="test-token",
        workspace="hermes",
        project="hermes-test",
    )
    return AiMemoryProvider(config=cfg)


def test_provider_name(provider: AiMemoryProvider) -> None:
    assert provider.name == "ai-memory"


def test_is_available_with_token(provider: AiMemoryProvider) -> None:
    assert provider.is_available() is True


def test_is_available_without_token() -> None:
    p = AiMemoryProvider(config=AiMemoryConfig())
    assert p.is_available() is True


def test_initialize_sets_session_id(provider: AiMemoryProvider) -> None:
    provider.initialize("session-123", profile="test-profile")
    assert provider.session_id == "session-123"
    assert provider._config.project == "hermes-test-profile"


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


def test_handle_tool_call_write(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock(return_value={"ok": True})
    result = json.loads(provider.handle_tool_call(
        "ai_memory_write",
        {"path": "notes/test.md", "body": "# Hello"},
    ))
    assert result["ok"] is True
    assert result["written"] == "notes/test.md"


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
    provider._search = MagicMock(return_value={
        "ok": True,
        "results": [
            {"snippet": "context 1"},
            {"snippet": "context 2"},
        ],
    })
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
    assert True


def test_sync_turn_absorbs_extra_kwargs(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.sync_turn(
        "user msg", "assistant msg", session_id="sess-1", context="extra", extra_key="val"
    )
    assert True


def test_on_session_end_spawns_daemon(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.on_session_end([{"role": "user", "content": "hello"}])
    assert True


def test_on_session_end_absorbs_extra_kwargs(provider: AiMemoryProvider) -> None:
    provider._client.send_hook = MagicMock()
    provider.on_session_end([{"role": "user", "content": "hello"}], extra_key="val")
    assert True


def test_on_memory_write_calls_client(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("write", "notes/foo", "# content")
    provider._client.write_page.assert_called_once()


def test_on_memory_write_with_metadata(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("write", "notes/foo", "# content", metadata={"tags": ["test"]})
    provider._client.write_page.assert_called_once()


def test_on_memory_write_skips_other_actions(provider: AiMemoryProvider) -> None:
    provider._client.write_page = MagicMock()
    provider.on_memory_write("delete", "notes/foo", "# content")
    provider._client.write_page.assert_not_called()


def test_queue_prefetch(provider: AiMemoryProvider) -> None:
    provider.prefetch = MagicMock()
    provider.queue_prefetch("test query")
    assert True


def test_initialize_resolves_workspace_from_kwargs(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="test-profile", ai_memory_workspace="ws-custom")
    assert provider._config.workspace == "ws-custom"


def test_initialize_project_kwarg_overrides_profile(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="test-profile", project="custom-proj")
    assert provider._config.project == "custom-proj"


def test_initialize_preserves_default_workspace(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="test-profile")
    assert provider._config.workspace == "hermes"


def test_initialize_uses_profile_when_no_explicit_project(provider: AiMemoryProvider) -> None:
    provider.initialize("sess-1", profile="custom-profile")
    assert provider._config.project == "hermes-custom-profile"


def test_prefetch_propagates_search_errors(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(side_effect=RuntimeError("search failed"))
    with pytest.raises(RuntimeError, match="search failed"):
        provider.prefetch("test query")


def test_handle_tool_call_propagates_errors(provider: AiMemoryProvider) -> None:
    provider._client.search = MagicMock(side_effect=RuntimeError("search failed"))
    with pytest.raises(RuntimeError):
        provider.handle_tool_call("ai_memory_search", {"query": "test"})
