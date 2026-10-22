from __future__ import annotations

import json
import sys
import types
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


def test_plugin_yaml_declares_python_dependency() -> None:
    # Hermes validates `python_dependencies`; `pip_dependencies` is an unknown
    # manifest key (warned and ignored), so the dependency has to be declared
    # under the spelling the loader knows.
    with open(PLUGIN_YAML) as f:
        data = yaml.safe_load(f)
    assert "httpx" in data.get("python_dependencies", [])
    assert "pip_dependencies" not in data
    assert "entry_point" not in data


def test_plugin_yaml_is_exclusive_without_hook_declarations() -> None:
    # A memory provider is selected by name (`memory.provider`) and its hooks
    # are ABC methods, not event-bus events; declaring them advertised names
    # no event bus ever delivers.
    with open(PLUGIN_YAML) as f:
        data = yaml.safe_load(f)
    assert data.get("kind") == "exclusive"
    assert "hooks" not in data


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


@pytest.mark.parametrize("source", ["file", "env"])
def test_register_loads_search_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    from __init__ import register

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    if source == "file":
        (tmp_path / "ai-memory.json").write_text(json.dumps({"search_scope": "project"}))
    else:
        monkeypatch.setenv("AI_MEMORY_SEARCH_SCOPE", "project")
    ctx = MagicMock()
    register(ctx)
    provider = ctx.register_memory_provider.call_args.args[0]
    assert provider._config.search_scope == "project"


def test_register_prefers_hermes_get_hermes_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hermes' resolver (context override → env → default) wins over raw env."""
    from __init__ import register

    context_home = tmp_path / "context-home"
    context_home.mkdir()
    (context_home / "ai-memory.json").write_text(
        json.dumps({"server_url": "http://context-home:49374"})
    )
    fake = types.ModuleType("hermes_constants")
    fake.get_hermes_home = lambda: context_home  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", fake)
    # A different env home must lose to the host's context override.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "env-home"))
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)

    ctx = MagicMock()
    register(ctx)
    provider = ctx.register_memory_provider.call_args.args[0]
    assert provider._config.server_url == "http://context-home:49374"


def test_register_falls_back_to_env_home_when_hermes_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plugin must still load standalone, without Hermes on sys.path."""
    from __init__ import register

    hermes_home = tmp_path / "env-home"
    hermes_home.mkdir()
    (hermes_home / "ai-memory.json").write_text(
        json.dumps({"server_url": "http://env-home:49374"})
    )
    # An empty module makes ``from hermes_constants import get_hermes_home``
    # raise ImportError, exercising the standalone fallback path.
    monkeypatch.setitem(sys.modules, "hermes_constants", types.ModuleType("hermes_constants"))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)

    ctx = MagicMock()
    register(ctx)
    provider = ctx.register_memory_provider.call_args.args[0]
    assert provider._config.server_url == "http://env-home:49374"
