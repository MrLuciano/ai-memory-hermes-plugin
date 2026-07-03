from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from config import AiMemoryConfig, get_config_schema, load_config, save_config


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


def test_load_config_from_file(tmp_path: Path) -> None:
    p = tmp_path / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "server_url": "http://file:49374",
        "auth_token": "file-token",
        "workspace": "file-ws",
        "project": "file-proj",
    }))
    cfg = load_config(str(tmp_path))
    assert cfg.server_url == "http://file:49374"
    assert cfg.auth_token == "file-token"
    assert cfg.workspace == "file-ws"
    assert cfg.project == "file-proj"


def test_load_config_file_not_found(tmp_path: Path) -> None:
    old_url = os.environ.pop("AI_MEMORY_SERVER_URL", None)
    old_token = os.environ.pop("AI_MEMORY_AUTH_TOKEN", None)
    try:
        cfg = load_config(str(tmp_path))
        assert cfg.server_url == "http://127.0.0.1:49374"
        assert cfg.auth_token == ""
    finally:
        if old_url is not None:
            os.environ["AI_MEMORY_SERVER_URL"] = old_url
        if old_token is not None:
            os.environ["AI_MEMORY_AUTH_TOKEN"] = old_token


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
