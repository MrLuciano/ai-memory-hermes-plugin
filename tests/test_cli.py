from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_register_cli_creates_subcommands() -> None:
    from cli import register_cli

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register_cli(subparsers)
    assert subparsers.choices is not None
    assert "status" in subparsers.choices
    assert "config" in subparsers.choices
    assert "link" in subparsers.choices


def test_cmd_status_reachable(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_status

    mock_client = MagicMock()
    mock_client.status.return_value = {"ok": True, "pages": 10, "sessions": 5}

    with patch("cli.AiMemoryClient", return_value=mock_client):
        args = argparse.Namespace(hermes_home=str(tmp_path))
        cmd_status(args)

    captured = capsys.readouterr()
    assert "reachable" in captured.out or "10 pages" in captured.out or "5 sessions" in captured.out


def test_cmd_status_unreachable(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_status

    mock_client = MagicMock()
    mock_client.status.side_effect = ConnectionError("Server refused connection")

    with patch("cli.AiMemoryClient", return_value=mock_client):
        args = argparse.Namespace(hermes_home=str(tmp_path))
        cmd_status(args)

    captured = capsys.readouterr()
    assert "unreachable" in captured.out.lower() or "error" in captured.out.lower()


def test_cmd_config_shows_values(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_config

    monkeypatch.delenv("AI_MEMORY_SERVER_URL", raising=False)
    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    config_dir = tmp_path / ".hermes"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "ai-memory.json"
    config_file.write_text(
        json.dumps({"server_url": "http://custom:49374", "project": "custom-project"})
    )

    args = argparse.Namespace(hermes_home=str(config_dir))
    cmd_config(args)

    captured = capsys.readouterr()
    assert "http://custom:49374" in captured.out
    assert "custom-project" in captured.out


def test_cmd_config_missing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_config

    args = argparse.Namespace(hermes_home=str(tmp_path / ".hermes"))
    cmd_config(args)

    captured = capsys.readouterr()
    assert captured.out


def test_cmd_link_creates_symlink(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_link

    plugin_dir = tmp_path / "plugins" / "memory" / "ai-memory"
    plugin_dir.mkdir(parents=True)

    hermes_plugins = tmp_path / "hermes" / "plugins"
    hermes_plugins.mkdir(parents=True)

    with (
        patch("cli.PLUGIN_DIR", str(plugin_dir)),
        patch("cli.os.path.islink", return_value=False),
        patch("cli.os.symlink") as mock_symlink,
    ):
        args = argparse.Namespace(hermes_home=str(hermes_plugins.parent))
        cmd_link(args)

    mock_symlink.assert_called_once()
    captured = capsys.readouterr()
    assert "linked" in captured.out.lower()


def test_cmd_link_already_linked(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_link

    plugin_dir = tmp_path / "plugins" / "memory" / "ai-memory"
    plugin_dir.mkdir(parents=True)

    hermes_plugins = tmp_path / "hermes" / "plugins"
    hermes_plugins.mkdir(parents=True)

    with (
        patch("cli.PLUGIN_DIR", str(plugin_dir)),
        patch("cli.os.path.islink", return_value=False),
        patch("cli.os.symlink", side_effect=FileExistsError),
    ):
        args = argparse.Namespace(hermes_home=str(hermes_plugins.parent))
        cmd_link(args)

    captured = capsys.readouterr()
    assert "already" in captured.out.lower()
