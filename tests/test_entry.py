from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

PLUGIN_YAML = Path(__file__).parent.parent / "plugins/memory/ai-memory/plugin.yaml"


def test_register_exists() -> None:
    from __init__ import register

    assert callable(register)


def test_register_returns_none() -> None:
    from __init__ import register

    ctx = MagicMock()
    result = register(ctx)
    assert result is None


def test_register_calls_register_memory_provider() -> None:
    from __init__ import register

    ctx = MagicMock()
    register(ctx)
    ctx.register_memory_provider.assert_called_once()


def test_register_passes_ai_memory_provider_instance() -> None:
    from __init__ import register
    from provider import AiMemoryProvider

    ctx = MagicMock()
    register(ctx)
    args, _ = ctx.register_memory_provider.call_args
    assert len(args) >= 1
    assert isinstance(args[0], AiMemoryProvider)


def test_plugin_yaml_has_httpx_dependency() -> None:
    with open(PLUGIN_YAML) as f:
        data = yaml.safe_load(f)
    deps = data.get("pip_dependencies", [])
    assert "httpx" in deps


def test_plugin_yaml_has_on_session_end_hook() -> None:
    with open(PLUGIN_YAML) as f:
        data = yaml.safe_load(f)
    hooks = data.get("hooks", [])
    assert "on_session_end" in hooks


def test_registered_provider_has_config_schema() -> None:
    from __init__ import register

    ctx = MagicMock()
    register(ctx)
    args, _ = ctx.register_memory_provider.call_args
    provider = args[0]
    schema = provider.get_config_schema()
    assert isinstance(schema, list)
    assert len(schema) > 0


def test_register_loads_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from __init__ import register

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    config_file = hermes_home / "ai-memory.json"
    config_file.write_text(
        json.dumps({"server_url": "http://custom:49374", "project": "custom-project"})
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)

    ctx = MagicMock()
    register(ctx)
    args, _ = ctx.register_memory_provider.call_args
    provider = args[0]
    assert provider._config.server_url == "http://custom:49374"
    assert provider._config.project == "custom-project"
    assert provider._config.workspace == "hermes"


def test_register_handles_corrupt_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from __init__ import register

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    config_file = hermes_home / "ai-memory.json"
    config_file.write_text("not valid json")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)

    ctx = MagicMock()
    register(ctx)
    args, _ = ctx.register_memory_provider.call_args
    provider = args[0]
    assert provider._config.server_url == "http://127.0.0.1:49374"


def test_register_uses_env_var_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from __init__ import register

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("AI_MEMORY_SERVER_URL", "http://env-override:49374")
    monkeypatch.setenv("AI_MEMORY_AUTH_TOKEN", "env-token")

    ctx = MagicMock()
    register(ctx)
    args, _ = ctx.register_memory_provider.call_args
    provider = args[0]
    assert provider._config.server_url == "http://env-override:49374"
    assert provider._config.auth_token == "env-token"
