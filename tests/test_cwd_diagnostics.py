"""Local scope diagnostics: no active profile, server, or memory writes."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from config import AiMemoryConfig, marker_scope
from provider import AiMemoryProvider


def test_missing_host_cwd_is_visible_without_network(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    client = MagicMock()
    monkeypatch.setattr("provider.AiMemoryClient", lambda config: client)
    provider = AiMemoryProvider(config=AiMemoryConfig(search_scope="project"))
    with caplog.at_level(logging.INFO, logger="provider"):
        provider.initialize("session", agent_workspace="hermes", agent_identity="default")
    diagnostics = provider.scope_diagnostics()
    assert diagnostics == {
        "cwd_received": "", "cwd_source": "", "cwd_normalized": "",
        "search_scope": "project",
        "workspace": "hermes", "project": "hermes-default",
        "workspace_source": "", "project_source": "", "scope_known": False,
        "writes_allowed": False, "project_search_allowed": False,
    }
    assert "cwd_received=''" in caplog.text
    assert "scope_known=False" in caplog.text
    assert not client.mock_calls


def test_native_windows_scope_diagnostics_use_nearest_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    root = tmp_path / "imperio_2026"
    app = root / "apps" / "socorro_financeiro"
    app.mkdir(parents=True)
    (root / ".ai-memory.toml").write_text('workspace = "hermes"\nproject = "imperio_2026"\n')
    (app / ".ai-memory.toml").write_text(
        'workspace = "hermes"\nproject = "socorro-financeiro"\n'
    )
    client = MagicMock()
    client.fetch_handoff.return_value = "SECRET_MEMORY_CONTENT"
    monkeypatch.setattr("provider.AiMemoryClient", lambda config: client)
    provider = AiMemoryProvider(config=AiMemoryConfig(
        search_scope="project", auth_token="SECRET_TOKEN", api_key="SECRET_KEY",
    ))
    with caplog.at_level(logging.INFO, logger="provider"):
        provider.initialize("session", cwd=str(app))
    client.reset_mock()
    diagnostics = provider.scope_diagnostics()
    assert diagnostics["cwd_received"] == str(app)
    assert diagnostics["cwd_normalized"] == str(app)
    assert diagnostics["project"] == "socorro-financeiro"
    assert diagnostics["scope_known"] is True
    assert diagnostics["writes_allowed"] is True
    assert diagnostics["project_search_allowed"] is True
    assert not client.mock_calls  # Reading diagnostics itself never fetches a handoff.
    assert "socorro-financeiro" in caplog.text
    assert "SECRET" not in caplog.text
    assert "SECRET" not in str(diagnostics)


@pytest.mark.parametrize("kind", ["missing", "relative", "file", "rooted", "drive-relative"])
def test_invalid_cwd_diagnostics_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    (tmp_path / ".ai-memory.toml").write_text('workspace = "hermes"\nproject = "root"\n')
    file = tmp_path / "file.py"
    file.write_text("pass\n")
    paths = {
        "missing": str(tmp_path / "missing"), "relative": "apps/socorro_financeiro",
        "file": str(file), "rooted": r"\imperio_2026", "drive-relative": "C:apps",
    }
    if kind in ("rooted", "drive-relative") and tmp_path.drive == "":
        pytest.skip("Windows-specific ambiguous paths")
    client = MagicMock()
    monkeypatch.setattr("provider.AiMemoryClient", lambda config: client)
    provider = AiMemoryProvider(config=AiMemoryConfig(search_scope="project"))
    provider.initialize("session", cwd=paths[kind])
    diagnostics = provider.scope_diagnostics()
    assert diagnostics["cwd_received"] == paths[kind]
    assert diagnostics["cwd_normalized"] == ""
    assert diagnostics["scope_known"] is False
    assert not provider._search({"query": "private"})["ok"]
    assert not provider._write({"path": "note.md", "body": "private"})["ok"]
    provider.prefetch("private")
    provider.queue_prefetch("private")
    provider.sync_turn("private", "private")
    provider.on_session_end([])
    provider.on_memory_write("add", "memory", "private")
    assert not client.mock_calls


def test_windows_msys_representation_is_not_assumed_to_be_host_cwd(tmp_path: Path) -> None:
    if not tmp_path.drive:
        pytest.skip("Native Windows filesystem required")
    (tmp_path / ".ai-memory.toml").write_text('project = "native"\n')
    msys = "/" + tmp_path.drive[0].lower() + tmp_path.as_posix()[2:]
    assert marker_scope(str(tmp_path)) == {"project": "native"}
    assert marker_scope(msys) == {}


def test_diagnostics_reinitialize_clears_previous_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".ai-memory.toml").write_text('workspace = "hermes"\nproject = "app"\n')
    client = MagicMock()
    client.fetch_handoff.return_value = None
    monkeypatch.setattr("provider.AiMemoryClient", lambda config: client)
    provider = AiMemoryProvider(config=AiMemoryConfig(search_scope="project"))
    provider.initialize("old", cwd=str(tmp_path))
    assert provider.scope_diagnostics()["scope_known"]
    provider.initialize("new")
    diagnostics: dict[str, Any] = provider.scope_diagnostics()
    assert diagnostics["cwd_normalized"] == ""
    assert diagnostics["scope_known"] is False
