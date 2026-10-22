from __future__ import annotations

import json
from pathlib import Path

import pytest
from config import (
    AiMemoryConfig,
    _secret_keys,
    explicit_scope_keys,
    get_config_schema,
    load_config,
    marker_briefing,
    marker_scope,
    save_config,
)


def test_config_defaults() -> None:
    cfg = AiMemoryConfig()
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.api_key == ""
    assert cfg.auth_token == ""
    assert cfg.workspace == "hermes"
    assert cfg.project == "hermes-default"


def test_config_custom_values() -> None:
    cfg = AiMemoryConfig(
        server_url="http://custom:49374",
        auth_token="abc123",
        workspace="custom-ws",
        project="custom-proj",
    )
    assert cfg.server_url == "http://custom:49374"
    assert cfg.auth_token == "abc123"
    assert cfg.workspace == "custom-ws"
    assert cfg.project == "custom-proj"


def test_get_config_schema() -> None:
    schema = get_config_schema()
    keys = {item["key"] for item in schema}
    assert "server_url" in keys
    assert "api_key" in keys
    assert "auth_token" in keys
    assert "workspace" in keys
    assert "project" in keys


def test_save_config_creates_file(tmp_path: Path) -> None:
    save_config({"server_url": "http://test:49374"}, str(tmp_path))
    p = tmp_path / "ai-memory.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["server_url"] == "http://test:49374"


def test_save_config_merges_existing(tmp_path: Path) -> None:
    p = tmp_path / "ai-memory.json"
    p.write_text(json.dumps({"existing_key": "value"}))
    save_config({"server_url": "http://test:49374"}, str(tmp_path))
    data = json.loads(p.read_text())
    assert data["existing_key"] == "value"
    assert data["server_url"] == "http://test:49374"


def test_load_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "server_url": "http://file:49374",
                "auth_token": "file-token",
                "workspace": "file-ws",
                "project": "file-proj",
            }
        )
    )
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://file:49374"
    assert cfg.auth_token == "file-token"
    assert cfg.workspace == "file-ws"
    assert cfg.project == "file-proj"


def test_load_config_file_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.auth_token == ""


def test_save_config_creates_parent_dirs(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    save_config({"server_url": "http://test:49374"}, str(deep))
    assert (deep / "ai-memory.json").exists()


def test_load_config_falls_back_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MEMORY_SERVER_URL", "http://env:49374")
    monkeypatch.setenv("AI_MEMORY_AUTH_TOKEN", "env-token")
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://env:49374"
    assert cfg.auth_token == "env-token"


def test_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    values = {
        "server_url": "http://roundtrip:49374",
        "auth_token": "roundtrip-token",
        "workspace": "roundtrip-ws",
        "project": "roundtrip-proj",
    }
    skipped = save_config(values, str(tmp_path))
    assert "auth_token" in skipped
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://roundtrip:49374"
    assert cfg.auth_token == ""  # secret was not written to disk
    assert cfg.workspace == "roundtrip-ws"
    assert cfg.project == "roundtrip-proj"


def test_load_config_corrupt_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not valid json")
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://127.0.0.1:49374"
    assert cfg.auth_token == ""


def test_load_config_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "server_url": "http://file:49374",
                "auth_token": "file-token",
            }
        )
    )
    monkeypatch.setenv("AI_MEMORY_SERVER_URL", "http://env:49374")
    monkeypatch.setenv("AI_MEMORY_AUTH_TOKEN", "env-token")
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://env:49374"
    assert cfg.auth_token == "env-token"


def test_load_config_filters_extra_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "server_url": "http://extra:49374",
                "auth_token": "extra-token",
                "unknown_key": "should be ignored",
            }
        )
    )
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://extra:49374"
    assert not hasattr(cfg, "unknown_key")


def test_save_config_does_not_write_secrets_to_disk(tmp_path: Path) -> None:
    skipped = save_config(
        {"server_url": "http://test:49374", "auth_token": "secret123", "api_key": "key456"},
        str(tmp_path),
    )
    assert "auth_token" in skipped
    assert "api_key" in skipped
    data = json.loads((tmp_path / "ai-memory.json").read_text())
    assert data["server_url"] == "http://test:49374"
    assert "auth_token" not in data
    assert "api_key" not in data


def test_save_config_strips_existing_secrets_from_file(tmp_path: Path) -> None:
    p = tmp_path / "ai-memory.json"
    p.write_text(
        json.dumps(
            {
                "server_url": "http://old:49374",
                "auth_token": "old-secret",
                "api_key": "old-key",
            }
        )
    )
    save_config({"server_url": "http://new:49374"}, str(tmp_path))
    data = json.loads(p.read_text())
    assert data["server_url"] == "http://new:49374"
    assert "auth_token" not in data
    assert "api_key" not in data


def test_save_config_returns_skipped_secrets(tmp_path: Path) -> None:
    skipped = save_config(
        {"auth_token": "tok", "api_key": "key", "workspace": "ws"},
        str(tmp_path),
    )
    assert set(skipped) == {"auth_token", "api_key"}
    data = json.loads((tmp_path / "ai-memory.json").read_text())
    assert data["workspace"] == "ws"


def test_secret_keys_returns_env_var_mapping() -> None:
    secrets = _secret_keys()
    assert secrets["auth_token"] == "AI_MEMORY_AUTH_TOKEN"
    assert secrets["api_key"] == "AI_MEMORY_API_KEY"


def test_get_config_schema_has_env_only() -> None:
    schema = get_config_schema()
    for item in schema:
        if item["key"] in ("auth_token", "api_key"):
            assert item.get("secret") is True
            assert item.get("env_only") is True
            assert "env_var" in item


def test_load_config_reads_scope_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MEMORY_WORKSPACE", "env-ws")
    monkeypatch.setenv("AI_MEMORY_PROJECT", "env-proj")
    cfg = load_config(str(tmp_path))
    assert cfg.workspace == "env-ws"
    assert cfg.project == "env-proj"


def test_explicit_scope_keys_reports_only_operator_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AI_MEMORY_WORKSPACE", raising=False)
    monkeypatch.delenv("AI_MEMORY_PROJECT", raising=False)
    assert explicit_scope_keys(str(tmp_path)) == set()

    (tmp_path / "ai-memory.json").write_text(json.dumps({"project": "custom-project"}))
    assert explicit_scope_keys(str(tmp_path)) == {"project"}

    monkeypatch.setenv("AI_MEMORY_WORKSPACE", "env-ws")
    assert explicit_scope_keys(str(tmp_path)) == {"workspace", "project"}


def test_marker_scope_reads_the_nearest_scope_marker(tmp_path: Path) -> None:
    # tmp_path is outside the real $HOME, so make it a checkout: the walk stops
    # at the checkout root, which is exactly this marker's directory.
    (tmp_path / ".git").mkdir()
    (tmp_path / ".ai-memory.toml").write_text('workspace = "default"\nproject = "Caminhar"\n')
    nested = tmp_path / "app" / "src"
    nested.mkdir(parents=True)
    assert marker_scope(str(nested)) == {"workspace": "default", "project": "Caminhar"}


def test_marker_scope_skips_a_capture_only_marker(tmp_path: Path) -> None:
    """A marker with no scope key keeps the walk-up going, like the server's."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".ai-memory.toml").write_text('project = "repo-project"\n')
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / ".ai-memory.toml").write_text("[capture]\nhook_capture = false\n")
    assert marker_scope(str(nested)) == {"project": "repo-project"}


def test_marker_scope_ignores_single_quoted_values(tmp_path: Path) -> None:
    """ai-memory's reader accepts only double-quoted strings; so does ours."""
    (tmp_path / ".ai-memory.toml").write_text(
        "workspace = 'acme'\nproject = \"infra\"  # trailing comment\n"
    )
    assert marker_scope(str(tmp_path)) == {"project": "infra"}


def test_marker_scope_is_empty_without_cwd_or_marker(tmp_path: Path) -> None:
    assert marker_scope("") == {}
    assert marker_scope(str(tmp_path)) == {}


def _briefing_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> tuple[Path, Path]:
    """A repository under a fake ``$HOME`` so the walk never reads the real one."""
    home = tmp_path / "home"
    repo = home / "repo"
    nested = repo / "src"
    nested.mkdir(parents=True)
    (repo / ".ai-memory.toml").write_text(marker, encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return repo, nested


def test_marker_briefing_reads_quoted_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, nested = _briefing_repo(
        tmp_path,
        monkeypatch,
        '[briefing]\ninject_on_session_start = "true"\nmax_chars = 6000\n',
    )
    assert marker_briefing(str(nested)) == {
        "inject_on_session_start": "true",
        "max_chars": "6000",
    }


def test_marker_briefing_accepts_bare_flags_and_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section-style flags may be bare, like the official hook clients read them."""
    _, nested = _briefing_repo(
        tmp_path,
        monkeypatch,
        '\ufeff[briefing]\ninject_on_session_start = yes  # opt in\nmax_chars = "5000"\n',
    )
    assert marker_briefing(str(nested)) == {
        "inject_on_session_start": "yes",
        "max_chars": "5000",
    }


def test_marker_briefing_skips_a_capture_only_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, nested = _briefing_repo(
        tmp_path,
        monkeypatch,
        "[briefing]\ninject_on_session_start = true\n",
    )
    (nested / ".ai-memory.toml").write_text('[capture]\nignore_paths = ["secret/**"]\n')
    assert marker_briefing(str(nested)) == {
        "inject_on_session_start": "true",
        "max_chars": "",
    }


def test_marker_briefing_stops_at_a_settings_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nearer marker that declares settings ends the walk, opt-in or not."""
    _, nested = _briefing_repo(
        tmp_path,
        monkeypatch,
        "[briefing]\ninject_on_session_start = true\n",
    )
    (nested / ".ai-memory.toml").write_text('workspace = "inner"\n')
    assert marker_briefing(str(nested)) == {"inject_on_session_start": "", "max_chars": ""}


def test_marker_briefing_is_empty_without_cwd_or_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    empty = home / "empty"
    empty.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert marker_briefing("") == {}
    assert marker_briefing(str(empty)) == {}
