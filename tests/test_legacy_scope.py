"""Legacy configuration provenance and CLI regressions; no real services."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import pytest
from cli import cmd_config, cmd_config_set
from config import AiMemoryConfig, explicit_scope_keys, get_config_schema, load_config, save_config
from provider import AiMemoryProvider


@pytest.mark.parametrize("scope_origin", [None, "automatic", "explicit"])
@pytest.mark.parametrize("directory,workspace,project", [
    ("src", "imperio", "imperio_2026"),
    ("apps/socorro_financeiro/src", "financeiro", "socorro_financeiro"),
])
def test_legacy_defaults_route_to_nearest_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    directory: str, workspace: str, project: str, scope_origin: str | None,
) -> None:
    root = tmp_path / "imperio_2026"
    app = root / "apps" / "socorro_financeiro"
    (root / "src").mkdir(parents=True)
    (app / "src").mkdir(parents=True)
    # tmp_path is outside $HOME; this checkout root is the walk boundary.
    (root / ".git").mkdir()
    (root / ".ai-memory.toml").write_text('workspace = "imperio"\nproject = "imperio_2026"\n')
    (app / ".ai-memory.toml").write_text(
        'workspace = "financeiro"\nproject = "socorro_financeiro"\n'
    )
    home = tmp_path / "legacy"
    home.mkdir()
    config_file = home / "ai-memory.json"
    values = {"workspace": "hermes", "project": "hermes-default", "search_scope": "project"}
    if scope_origin is not None:
        values["scope_origin"] = scope_origin
    if scope_origin == "explicit":
        workspace, project = "hermes", "hermes-default"
    config_file.write_text(json.dumps(values), encoding="utf-8-sig")
    before = config_file.read_bytes()
    requests: list[httpx.Request] = []

    from client import AiMemoryClient

    def factory(config: AiMemoryConfig) -> AiMemoryClient:
        client = AiMemoryClient(config)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/handoff":
                return httpx.Response(404)
            body = [] if request.url.path == "/admin/search" else {"ok": True}
            return httpx.Response(200, json=body)

        client._transport = httpx.MockTransport(handler)
        return client

    monkeypatch.setattr("provider.AiMemoryClient", factory)
    provider = AiMemoryProvider()
    provider.initialize("legacy", cwd=str(root / directory), hermes_home=str(home))
    assert provider._search({"query": "private"})["ok"]
    assert requests[-1].url.params["project"] == project
    assert requests[-1].url.params["workspace"] == workspace
    assert provider._write({"path": "note.md", "body": "private"})["ok"]
    assert json.loads(requests[-1].content)["project"] == project
    assert config_file.read_bytes() == before


def test_saving_intentional_default_pair_records_provenance(tmp_path: Path) -> None:
    save_config({"search_scope": "project", "workspace": "hermes", "project": "hermes-default"},
                str(tmp_path))
    data = json.loads((tmp_path / "ai-memory.json").read_text())
    assert data["scope_origin"] == "explicit"
    assert explicit_scope_keys(str(tmp_path)) == {"workspace", "project"}


@pytest.mark.parametrize("mode", ["global", "project"])
def test_cli_reports_search_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str,
) -> None:
    cmd_config_set(argparse.Namespace(hermes_home=str(tmp_path), key="search_scope", value=mode))
    capsys.readouterr()
    cmd_config(argparse.Namespace(hermes_home=str(tmp_path)))
    assert f"search_scope: {mode}" in capsys.readouterr().out


def test_setup_schema_does_not_generate_fixed_scope(tmp_path: Path) -> None:
    values = {field["key"]: field["default"] for field in get_config_schema() if "default" in field}
    save_config(values, str(tmp_path))
    assert explicit_scope_keys(str(tmp_path)) == set()
    assert load_config(str(tmp_path)).search_scope == "global"


@pytest.mark.parametrize("values,expected", [
    ({"workspace": "hermes", "project": "hermes-default"}, {"workspace", "project"}),
    ({"workspace": "hermes", "project": "hermes-default", "search_scope": "project"}, set()),
    ({"workspace": "hermes", "project": "hermes-default", "search_scope": "project",
      "scope_origin": "explicit"}, {"workspace", "project"}),
    ({"project": "hermes-default", "search_scope": "project"}, {"project"}),
    ({"workspace": "custom", "project": "hermes-default", "search_scope": "project"},
     {"workspace", "project"}),
    ({"workspace": "hermes", "project": "custom", "search_scope": "project"},
     {"workspace", "project"}),
    ({"workspace": "hermes", "project": "hermes-default", "search_scope": "project",
      "custom_option": True}, {"workspace", "project"}),
])
def test_legacy_classification_is_narrow(
    tmp_path: Path, values: dict[str, object], expected: set[str],
) -> None:
    (tmp_path / "ai-memory.json").write_text(json.dumps(values))
    assert explicit_scope_keys(str(tmp_path)) == expected


def test_environment_defaults_are_always_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "ai-memory.json").write_text(json.dumps({
        "workspace": "hermes", "project": "hermes-default",
    }))
    monkeypatch.setenv("AI_MEMORY_SEARCH_SCOPE", "project")
    assert explicit_scope_keys(str(tmp_path)) == set()
    monkeypatch.setenv("AI_MEMORY_WORKSPACE", "hermes")
    monkeypatch.setenv("AI_MEMORY_PROJECT", "hermes-default")
    assert explicit_scope_keys(str(tmp_path)) == {"workspace", "project"}


@pytest.mark.parametrize("key", ["search_scope", "scope_origin"])
def test_cli_invalid_policy_does_not_change_file(tmp_path: Path, key: str) -> None:
    save_config({"server_url": "http://example.invalid"}, str(tmp_path))
    before = (tmp_path / "ai-memory.json").read_bytes()
    with pytest.raises(ValueError, match=key):
        cmd_config_set(argparse.Namespace(hermes_home=str(tmp_path), key=key, value="invalid"))
    assert (tmp_path / "ai-memory.json").read_bytes() == before


@pytest.mark.parametrize("script", ["install.sh", "update.sh", "install.ps1", "update.ps1"])
def test_installer_templates_do_not_pin_scope(script: str) -> None:
    import re

    text = (Path(__file__).parents[1] / "scripts" / script).read_text(encoding="utf-8-sig")
    if script.endswith(".sh"):
        match = re.search(r'cat > "\$CONFIG_FILE" <<EOF\n(.*?)\nEOF', text, re.DOTALL)
        assert match
        values = json.loads(match.group(1))
    else:
        match = re.search(r'\$(?:Config|defaultConfig) = @{(.*?)\n        }', text, re.DOTALL)
        assert match
        values = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', match.group(1)))
    assert values["search_scope"] == "global"
    assert "workspace" not in values
    assert "project" not in values
