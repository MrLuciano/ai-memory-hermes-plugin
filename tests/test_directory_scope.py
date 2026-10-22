"""Filesystem/provider integration using temporary markers and an HTTP mock only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from client import AiMemoryClient
from config import AiMemoryConfig, get_config_schema, load_config, save_config
from provider import AiMemoryProvider


@pytest.fixture
def http_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AiMemoryProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/handoff":
            return httpx.Response(404)
        if request.url.path == "/admin/search":
            return httpx.Response(200, json=[{"snippet": "mock recall"}])
        return httpx.Response(200, json={"ok": True})

    def factory(config: AiMemoryConfig) -> AiMemoryClient:
        client = AiMemoryClient(config)
        client._transport = httpx.MockTransport(handler)
        return client

    monkeypatch.setattr("provider.AiMemoryClient", factory)
    return AiMemoryProvider(), requests


@pytest.mark.parametrize("mode", ["global", "project"])
def test_search_scope_config_roundtrip(tmp_path: Path, mode: str) -> None:
    config = AiMemoryConfig(search_scope=mode)
    assert config.search_scope == mode
    save_config({"search_scope": mode}, str(tmp_path))
    assert load_config(str(tmp_path)).search_scope == mode
    field = next(item for item in get_config_schema() if item["key"] == "search_scope")
    assert field["default"] == "global"
    assert set(field["choices"]) == {"global", "project"}


def test_global_search_is_the_default(
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    provider, requests = http_provider
    assert AiMemoryConfig().search_scope == "global"
    assert provider._search({"query": "shared"})["ok"]
    assert dict(requests[-1].url.params) == {"q": "shared", "limit": "5"}


@pytest.mark.parametrize("invalid", ["", "invalid", None])
def test_invalid_search_scope_is_rejected_without_writing(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(ValueError, match="search_scope"):
        AiMemoryConfig(search_scope=invalid)
    with pytest.raises(ValueError, match="search_scope"):
        save_config({"search_scope": invalid}, str(tmp_path))
    assert not (tmp_path / "ai-memory.json").exists()


@pytest.fixture
def deferred_workers(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    from types import SimpleNamespace

    workers: list[Any] = []

    def thread(*, target: Any, daemon: bool, name: str = "") -> SimpleNamespace:
        assert daemon
        return SimpleNamespace(start=lambda: workers.append(target), is_alive=lambda: False)

    monkeypatch.setattr("provider.threading.Thread", thread)
    return workers


@pytest.mark.parametrize("directory", ["absent", "missing", "file", "unmarked", "relative"])
def test_unknown_scope_blocks_every_write_and_handoff(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
    directory: str,
) -> None:
    provider, requests = http_provider
    # A process cwd marker must never become the session's implicit scope.
    repo = tmp_path / "imperio_2026"
    repo.mkdir()
    (repo / ".ai-memory.toml").write_text('workspace = "ws"\nproject = "root"\n')
    path = repo / "nonexistent"
    if directory == "absent":
        cwd = ""
    elif directory == "file":
        path = repo / "file.py"
        path.write_text("pass\n")
        cwd = str(path)
    elif directory == "unmarked":
        path = tmp_path / "unmarked"
        path.mkdir()
        cwd = str(path)
    elif directory == "relative":
        cwd = "imperio_2026"
    else:
        cwd = str(path)
    provider.initialize("unknown", cwd=cwd)
    result = provider._write({"path": "note.md", "body": "private"})
    assert result["ok"] is False
    assert "scope" in result["error"]
    provider.on_memory_write("add", "memory", "private")
    provider.sync_turn("private", "answer")
    provider.on_session_end([])
    assert not deferred_workers
    assert not requests


def test_reinitialize_does_not_reuse_previous_marker_project(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    provider, requests = http_provider
    repo = tmp_path / "imperio_2026"
    repo.mkdir()
    (repo / ".ai-memory.toml").write_text('workspace = "ws"\nproject = "imperio_2026"\n')
    provider.initialize("first", cwd=str(repo))
    assert provider._write({"path": "note.md", "body": "first"})["ok"]
    requests.clear()
    provider.initialize("second", cwd="")
    assert not provider._write({"path": "note.md", "body": "must not leak"})["ok"]
    assert not requests


@pytest.mark.parametrize("source", ["file", "env", "kwargs"])
def test_explicit_default_project_allows_writes_without_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    source: str,
) -> None:
    provider, requests = http_provider
    kwargs: dict[str, Any] = {}
    if source == "file":
        (tmp_path / "ai-memory.json").write_text(json.dumps({"project": "hermes-default"}))
        kwargs["hermes_home"] = str(tmp_path)
    elif source == "env":
        monkeypatch.setenv("AI_MEMORY_PROJECT", "hermes-default")
    else:
        kwargs["project"] = "hermes-default"
    provider.initialize("explicit", **kwargs)
    assert provider._write({"path": "note.md", "body": "allowed"})["ok"]
    payload = json.loads(requests[-1].content)
    assert payload["project"] == "hermes-default"
    assert payload["workspace"] == "hermes"


@pytest.fixture
def monorepo(tmp_path: Path) -> Path:
    root = tmp_path / "imperio_2026"
    app = root / "apps" / "socorro_financeiro"
    (app / "src").mkdir(parents=True)
    (root / "src").mkdir()
    # tmp_path is outside $HOME; this checkout root is the walk boundary.
    (root / ".git").mkdir()
    (root / ".ai-memory.toml").write_text(
        'workspace = "imperio"\nproject = "imperio_2026"\n'
    )
    (app / ".ai-memory.toml").write_text(
        'workspace = "financeiro"\nproject = "socorro_financeiro"\n'
    )
    return root


@pytest.mark.parametrize(
    "directory,workspace,project",
    [
        (".", "imperio", "imperio_2026"),
        ("src", "imperio", "imperio_2026"),
        ("apps/socorro_financeiro", "financeiro", "socorro_financeiro"),
        ("apps/socorro_financeiro/src", "financeiro", "socorro_financeiro"),
    ],
)
def test_nearest_toml_routes_search_writes_handoff_and_hooks(
    tmp_path: Path,
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
    directory: str,
    workspace: str,
    project: str,
) -> None:
    provider, requests = http_provider
    home = tmp_path / "profile"
    save_config({"search_scope": "project"}, str(home))
    cwd = str(monorepo / directory)
    provider.initialize("session", cwd=cwd, hermes_home=str(home), agent_workspace="hermes")
    assert dict(requests[-1].url.params) == {
        "agent": "hermes", "cwd": cwd, "workspace": workspace, "project": project,
    }
    assert provider._search({"query": "private"})["ok"]
    assert dict(requests[-1].url.params) == {
        "q": "private", "limit": "5", "workspace": workspace, "project": project,
    }
    provider._write({"path": "note.md", "body": "test"})
    provider.on_memory_write("add", "memory", "test")
    # The mirror is now background work (D4), so drain it before inspecting the
    # two synchronous write-page requests.
    deferred_workers.pop()()
    for request in requests[-2:]:
        body = json.loads(request.content)
        assert (body["workspace"], body["project"]) == (workspace, project)
    provider.sync_turn("test prompt", "test answer")
    provider.on_session_end([])
    for worker in deferred_workers:
        worker()
    for request in requests[-2:]:
        params = dict(request.url.params)
        assert (params["workspace"], params["project"]) == (workspace, project)
        assert params["cwd"] == cwd
        assert params["session_id"] == "session"


@pytest.mark.parametrize("source", ["file", "env", "kwargs"])
def test_explicit_scope_overrides_nested_toml(
    tmp_path: Path,
    monorepo: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    source: str,
) -> None:
    provider, requests = http_provider
    home = tmp_path / "profile"
    save_config({"search_scope": "project"}, str(home))
    kwargs: dict[str, Any] = {"hermes_home": str(home)}
    if source == "file":
        save_config({"workspace": "override-ws", "project": "override-project"}, str(home))
    elif source == "env":
        monkeypatch.setenv("AI_MEMORY_WORKSPACE", "override-ws")
        monkeypatch.setenv("AI_MEMORY_PROJECT", "override-project")
    else:
        kwargs.update(ai_memory_workspace="override-ws", project="override-project")
    provider.initialize("session", cwd=str(monorepo / "apps/socorro_financeiro/src"), **kwargs)
    provider._search({"query": "private"})
    assert requests[-1].url.params["workspace"] == "override-ws"
    assert requests[-1].url.params["project"] == "override-project"
    provider._write({"path": "note.md", "body": "allowed"})
    assert json.loads(requests[-1].content)["project"] == "override-project"


def test_project_search_does_not_fall_back_to_global_when_scope_is_unknown(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
) -> None:
    provider, requests = http_provider
    save_config({"search_scope": "project"}, str(tmp_path))
    provider.initialize("unknown", hermes_home=str(tmp_path))
    result = provider._search({"query": "private"})
    assert result["ok"] is False
    assert result["results"] == []
    assert provider.prefetch("private") == ""
    provider.queue_prefetch("private")
    assert not deferred_workers
    assert not requests


@pytest.mark.parametrize("mode", ["global", "project"])
def test_queue_prefetch_uses_configured_scope_and_real_cache_update(
    tmp_path: Path,
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
    mode: str,
) -> None:
    provider, requests = http_provider
    save_config({"search_scope": mode}, str(tmp_path))
    provider.initialize("session", cwd=str(monorepo), hermes_home=str(tmp_path))
    provider.queue_prefetch("test")
    assert not provider._prefetch_cache
    deferred_workers.pop()()
    key = ("session", mode, "imperio", "imperio_2026", "test")
    assert key in provider._prefetch_cache
    params = dict(requests[-1].url.params)
    expected = {"q": "test", "limit": "3"}
    if mode == "project":
        expected.update(workspace="imperio", project="imperio_2026")
    assert params == expected
    count = len(requests)
    assert provider.prefetch("test") == "mock recall"
    assert len(requests) == count


def test_queued_work_keeps_original_client_and_scope_after_reinitialize(
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
) -> None:
    provider, requests = http_provider
    provider.initialize("old", cwd=str(monorepo), ai_memory_server_url="http://old.invalid")
    provider.sync_turn("original", "answer")
    provider.on_session_end([])
    provider.queue_prefetch("old query")
    provider.initialize("new", cwd=str(monorepo / "apps/socorro_financeiro"))
    requests.clear()
    for worker in deferred_workers:
        worker()
    assert requests
    assert all(request.url.host == "old.invalid" for request in requests)
    for request in requests[:2]:
        assert request.url.params["project"] == "imperio_2026"
        assert request.url.params["session_id"] == "old"
    assert not provider._prefetch_cache  # A stale worker must not repopulate it.


def test_initialize_without_home_honors_search_scope_environment(
    monorepo: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    provider, requests = http_provider
    monkeypatch.setenv("AI_MEMORY_SEARCH_SCOPE", "project")
    provider.initialize("session", cwd=str(monorepo))
    provider._search({"query": "private"})
    assert requests[-1].url.params["project"] == "imperio_2026"


@pytest.mark.parametrize(
    ("marker", "writes_allowed"),
    [
        # Upstream derives the missing project (here: basename) instead of
        # disabling the marker's whole scope.
        ('workspace = "ws"\n', True),
        ('project = ""\n', False),
    ],
)
def test_marker_without_pinned_project_derives_or_stays_unscoped(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    marker: str,
    writes_allowed: bool,
) -> None:
    provider, requests = http_provider
    (tmp_path / ".ai-memory.toml").write_text(marker)
    provider.initialize("incomplete", cwd=str(tmp_path), agent_identity="profile")
    result = provider._write({"path": "note.md", "body": "private"})
    assert result["ok"] is writes_allowed
    if writes_allowed:
        payload = json.loads(requests[-1].content)
        assert payload["workspace"] == "ws"
        assert payload["project"] == tmp_path.name
    else:
        assert not requests


def test_cache_is_not_reused_between_search_modes(
    tmp_path: Path,
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
) -> None:
    provider, requests = http_provider
    provider.initialize("session", cwd=str(monorepo))
    provider.queue_prefetch("query")
    deferred_workers.pop()()
    provider._config.search_scope = "project"
    requests.clear()
    assert provider.prefetch("query") == "mock recall"
    assert requests[-1].url.params["project"] == "imperio_2026"


def test_session_switch_discards_late_cache_without_dynamic_scope_change(
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
    deferred_workers: list[Any],
) -> None:
    provider, requests = http_provider
    provider.initialize("old", cwd=str(monorepo))
    provider.queue_prefetch("query")
    provider.on_session_switch("new", cwd=str(monorepo / "apps/socorro_financeiro"))
    deferred_workers.pop()()
    assert not provider._prefetch_cache
    assert provider._config.project == "imperio_2026"
    provider._write({"path": "note.md", "body": "same construction scope"})
    assert json.loads(requests[-1].content)["project"] == "imperio_2026"


def test_failed_reinitialize_cannot_write_to_previous_project(
    tmp_path: Path,
    monorepo: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    provider, requests = http_provider
    provider.initialize("old", cwd=str(monorepo))
    (tmp_path / "ai-memory.json").write_text(json.dumps({"search_scope": "invalid"}))
    requests.clear()
    with pytest.raises(ValueError, match="search_scope"):
        provider.initialize("new", hermes_home=str(tmp_path))
    assert not provider._write({"path": "note.md", "body": "must not leak"})["ok"]
    assert not requests


# ------------------------------------------------------ runtime cwd resolution
def _install_runtime_cwd(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Fake the guarded ``agent.runtime_cwd`` import without installing Hermes."""
    agent_module = ModuleType("agent")
    agent_module.__path__ = []
    runtime_module = ModuleType("agent.runtime_cwd")
    setattr(runtime_module, "resolve_agent_cwd", lambda: directory)
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", runtime_module)


def test_initialize_without_cwd_uses_runtime_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    """Hermes omits ``cwd`` on the interactive CLI; resolving it must restore writes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".ai-memory.toml").write_text('workspace = "ws"\n')
    _install_runtime_cwd(monkeypatch, repo)

    provider, requests = http_provider
    provider.initialize("session")
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["cwd_source"] == "runtime"
    assert diagnostics["cwd_normalized"] == str(repo)
    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["project_source"] == "derived"
    assert diagnostics["scope_known"] is True
    assert diagnostics["writes_allowed"] is True
    assert provider._write({"path": "note.md", "body": "ok"})["ok"]
    assert json.loads(requests[-1].content)["project"] == "repo"


def test_ai_memory_cwd_overrides_kwarg_and_runtime_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    env_dir = tmp_path / "env-dir"
    kwarg_dir = tmp_path / "kwarg-dir"
    runtime_dir = tmp_path / "runtime-dir"
    for directory, workspace in (
        (env_dir, "env-ws"),
        (kwarg_dir, "kwarg-ws"),
        (runtime_dir, "runtime-ws"),
    ):
        directory.mkdir()
        (directory / ".ai-memory.toml").write_text(f'workspace = "{workspace}"\n')
    _install_runtime_cwd(monkeypatch, runtime_dir)
    monkeypatch.setenv("AI_MEMORY_CWD", str(env_dir))

    provider, requests = http_provider
    provider.initialize("session", cwd=str(kwarg_dir))
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["cwd_source"] == "environment"
    assert diagnostics["cwd_received"] == str(env_dir)
    assert diagnostics["workspace"] == "env-ws"
    assert diagnostics["project"] == "env-dir"
    assert provider._write({"path": "note.md", "body": "ok"})["ok"]
    payload = json.loads(requests[-1].content)
    assert (payload["workspace"], payload["project"]) == ("env-ws", "env-dir")


def test_nothing_resolvable_stays_read_only_and_is_diagnosable(
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    monkeypatch.delenv("AI_MEMORY_CWD", raising=False)
    monkeypatch.setitem(sys.modules, "agent", None)

    provider, requests = http_provider
    provider.initialize("session")
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["cwd_source"] == ""
    assert diagnostics["cwd_received"] == ""
    assert diagnostics["cwd_normalized"] == ""
    assert diagnostics["workspace_source"] == ""
    assert diagnostics["project_source"] == ""
    assert diagnostics["scope_known"] is False
    assert diagnostics["writes_allowed"] is False
    assert not provider._write({"path": "note.md", "body": "private"})["ok"]
    assert not requests


# --------------------------------------------------------- scope authorization
def test_workspace_only_marker_derives_project_and_authorizes_writes(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    """Upstream markers require workspace, project is optional; a derived project
    is a legitimate scope and must no longer disable every write."""
    (tmp_path / ".ai-memory.toml").write_text('workspace = "ws"\n')

    provider, requests = http_provider
    provider.initialize("session", cwd=str(tmp_path))
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["workspace"] == "ws"
    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["project"] == tmp_path.name
    assert diagnostics["project_source"] == "derived"
    assert diagnostics["scope_known"] is True
    assert diagnostics["writes_allowed"] is True
    assert provider._write({"path": "note.md", "body": "ok"})["ok"]
    payload = json.loads(requests[-1].content)
    assert (payload["workspace"], payload["project"]) == ("ws", tmp_path.name)


def test_dataclass_default_project_without_provenance_stays_read_only(
    monkeypatch: pytest.MonkeyPatch,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    monkeypatch.delenv("AI_MEMORY_CWD", raising=False)
    monkeypatch.setitem(sys.modules, "agent", None)

    provider, requests = http_provider
    provider.initialize("session")
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["project"] == "hermes-default"
    assert diagnostics["project_source"] == ""
    assert diagnostics["scope_known"] is False
    assert diagnostics["writes_allowed"] is False
    assert not provider._write({"path": "note.md", "body": "private"})["ok"]
    assert not requests


def test_explicit_project_outranks_a_derived_one(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    (tmp_path / ".ai-memory.toml").write_text('workspace = "ws"\n')

    provider, _ = http_provider
    provider.initialize("session", cwd=str(tmp_path), project="pinned-project")
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["project"] == "pinned-project"
    assert diagnostics["project_source"] == "explicit"
    assert diagnostics["scope_known"] is True


def test_marker_project_outranks_derivation(
    tmp_path: Path,
    http_provider: tuple[AiMemoryProvider, list[httpx.Request]],
) -> None:
    root = tmp_path / "repo"
    nested = root / "src"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".ai-memory.toml").write_text('workspace = "ws"\nproject = "pinned"\n')

    provider, _ = http_provider
    provider.initialize("session", cwd=str(nested))
    diagnostics = provider.scope_diagnostics()

    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["project"] == "pinned"
    assert diagnostics["project_source"] == "marker"
    assert diagnostics["scope_known"] is True
