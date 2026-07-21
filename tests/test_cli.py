from __future__ import annotations

import argparse
import json
import shutil
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
    assert "config-set" in subparsers.choices
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
    monkeypatch.delenv("AI_MEMORY_API_KEY", raising=False)
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
    assert "(not set)" in captured.out


def test_cmd_config_shows_env_source(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_config

    monkeypatch.setenv("AI_MEMORY_AUTH_TOKEN", "env-token-123")
    monkeypatch.delenv("AI_MEMORY_API_KEY", raising=False)
    config_dir = tmp_path / ".hermes"
    config_dir.mkdir(parents=True)
    (config_dir / "ai-memory.json").write_text(json.dumps({"server_url": "http://x:1"}))

    args = argparse.Namespace(hermes_home=str(config_dir))
    cmd_config(args)

    captured = capsys.readouterr()
    assert "set via env: AI_MEMORY_AUTH_TOKEN" in captured.out


def test_cmd_config_set_rejects_secrets(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from cli import cmd_config_set

    args = argparse.Namespace(
        hermes_home=str(tmp_path), key="auth_token", value="secret123"
    )
    cmd_config_set(args)

    captured = capsys.readouterr()
    assert "NOT WRITTEN TO DISK" in captured.out
    assert "AI_MEMORY_AUTH_TOKEN" in captured.out
    # Ensure nothing was written to disk
    assert not (tmp_path / "ai-memory.json").exists()


def test_cmd_config_set_allows_non_secrets(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from cli import cmd_config_set

    args = argparse.Namespace(
        hermes_home=str(tmp_path), key="workspace", value="my-ws"
    )
    cmd_config_set(args)

    captured = capsys.readouterr()
    assert "saved" in captured.out
    data = json.loads((tmp_path / "ai-memory.json").read_text())
    assert data["workspace"] == "my-ws"


def test_cmd_config_set_rejects_api_key(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from cli import cmd_config_set

    args = argparse.Namespace(
        hermes_home=str(tmp_path), key="api_key", value="key-abc"
    )
    cmd_config_set(args)

    captured = capsys.readouterr()
    assert "NOT WRITTEN TO DISK" in captured.out
    assert "AI_MEMORY_API_KEY" in captured.out


def test_cmd_config_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_config

    monkeypatch.delenv("AI_MEMORY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AI_MEMORY_API_KEY", raising=False)
    args = argparse.Namespace(hermes_home=str(tmp_path / ".hermes"))
    cmd_config(args)

    captured = capsys.readouterr()
    assert captured.out
    assert "(not set)" in captured.out


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


def _build_fake_tarball(dest: Path, plugin_dir: Path) -> None:
    """Create a zip archive that mimics the GitHub source tarball layout."""
    import zipfile

    prefix = "ai-memory-hermes-plugin-main/plugins/memory/ai-memory"
    with zipfile.ZipFile(dest, "w") as zf:
        for file in plugin_dir.rglob("*"):
            if file.is_file():
                arc_name = f"{prefix}/{file.relative_to(plugin_dir)}"
                zf.write(file, arc_name)


def test_cmd_update_registers_update_subcommand() -> None:
    from cli import register_cli

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register_cli(subparsers)
    assert "update" in subparsers.choices


def test_cmd_update_not_installed(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from cli import cmd_update

    args = argparse.Namespace(hermes_home=str(tmp_path / ".hermes"))
    cmd_update(args)

    captured = capsys.readouterr()
    assert "not installed" in captured.out


def test_cmd_update_from_github_preserves_config(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_update

    monkeypatch.delenv("UPDATE_FROM_LOCAL", raising=False)
    hermes_home = tmp_path / ".hermes"
    plugin_dir = hermes_home / "plugins" / "ai-memory"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("# old")
    config_file = hermes_home / "ai-memory.json"
    config_file.write_text(json.dumps({"server_url": "http://custom:49374"}))

    # Source files to "download"
    source_plugin = tmp_path / "source" / "ai-memory"
    source_plugin.mkdir(parents=True)
    (source_plugin / "__init__.py").write_text("# new")
    (source_plugin / "provider.py").write_text("# new provider")
    tarball = tmp_path / "repo.zip"
    _build_fake_tarball(tarball, source_plugin)

    def fake_urlretrieve(url: str, dest: str) -> None:
        shutil.copy(str(tarball), dest)

    with patch("cli.urllib.request.urlretrieve", side_effect=fake_urlretrieve):
        args = argparse.Namespace(hermes_home=str(hermes_home))
        cmd_update(args)

    captured = capsys.readouterr()
    assert "Done" in captured.out
    assert "Restart Hermes" in captured.out
    assert (plugin_dir / "__init__.py").read_text() == "# new"
    assert json.loads(config_file.read_text())["server_url"] == "http://custom:49374"
    backups = list((hermes_home / ".ai-memory-backups").glob("ai-memory.bak.*"))
    assert len(backups) == 1


def test_cmd_update_creates_default_config(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_update

    monkeypatch.delenv("UPDATE_FROM_LOCAL", raising=False)
    hermes_home = tmp_path / ".hermes"
    plugin_dir = hermes_home / "plugins" / "ai-memory"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("# old")

    source_plugin = tmp_path / "source" / "ai-memory"
    source_plugin.mkdir(parents=True)
    (source_plugin / "__init__.py").write_text("# new")
    tarball = tmp_path / "repo.zip"
    _build_fake_tarball(tarball, source_plugin)

    def fake_urlretrieve(url: str, dest: str) -> None:
        shutil.copy(str(tarball), dest)

    with patch("cli.urllib.request.urlretrieve", side_effect=fake_urlretrieve):
        args = argparse.Namespace(hermes_home=str(hermes_home))
        cmd_update(args)

    config_file = hermes_home / "ai-memory.json"
    assert config_file.exists()
    config = json.loads(config_file.read_text())
    assert config["server_url"] == "http://127.0.0.1:49374"
    assert config["workspace"] == "hermes"


def test_cmd_update_lists_multiple_backups(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli import cmd_update

    monkeypatch.delenv("UPDATE_FROM_LOCAL", raising=False)
    hermes_home = tmp_path / ".hermes"
    plugin_dir = hermes_home / "plugins" / "ai-memory"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("# old")

    # Pre-seed an older backup
    old_backup = hermes_home / ".ai-memory-backups" / "ai-memory.bak.20250101000000"
    old_backup.mkdir(parents=True)

    source_plugin = tmp_path / "source" / "ai-memory"
    source_plugin.mkdir(parents=True)
    (source_plugin / "__init__.py").write_text("# new")
    tarball = tmp_path / "repo.zip"
    _build_fake_tarball(tarball, source_plugin)

    def fake_urlretrieve(url: str, dest: str) -> None:
        shutil.copy(str(tarball), dest)

    with patch("cli.urllib.request.urlretrieve", side_effect=fake_urlretrieve):
        args = argparse.Namespace(hermes_home=str(hermes_home))
        cmd_update(args)

    captured = capsys.readouterr()
    assert captured.out.count("ai-memory.bak.") >= 2
    assert old_backup.name in captured.out
