"""Scope resolution must match the ai-memory marker contract.

The fixtures build synthetic checkouts - a ``.git/config`` with remote URLs -
so nothing touches the network, the real git configuration, or a subprocess.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from config import (
    _parse_marker_key,
    marker_briefing,
    marker_scope,
    resolve_scope,
)


@pytest.fixture(autouse=True)
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every walk deterministic and away from the real ``$HOME``."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _git_repo(path: Path, remotes: dict[str, str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git_dir = path / ".git"
    git_dir.mkdir()
    lines: list[str] = []
    for name, url in remotes.items():
        lines.extend([f'[remote "{name}"]', f"\turl = {url}"])
    (git_dir / "config").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _marker(directory: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".ai-memory.toml"
    marker.write_text(text, encoding="utf-8")
    return marker


# ---------------------------------------------------------------- derivation


def test_workspace_only_marker_derives_project_from_remote(fake_home: Path) -> None:
    """The regression: a workspace-only marker used to leave the project unknown."""
    repo = _git_repo(fake_home / "repo", {"origin": "git@github.com:acme/widget.git"})
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo)) == {"workspace": "acme", "project": "acme-widget"}


def test_workspace_only_marker_derives_remote_from_a_nested_cwd(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "git@github.com:acme/widget.git"})
    _marker(repo, 'workspace = "acme"\n')
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)

    assert marker_scope(str(nested)) == {"workspace": "acme", "project": "acme-widget"}


def test_workspace_only_marker_falls_back_to_basename(fake_home: Path) -> None:
    plain = fake_home / "plain"

    _marker(plain, 'workspace = "acme"\n')

    assert marker_scope(str(plain)) == {"workspace": "acme", "project": "plain"}


def test_project_comes_from_upstream_remote_when_both_exist(fake_home: Path) -> None:
    repo = _git_repo(
        fake_home / "repo",
        {
            "origin": "https://github.com/acme/origin.git",
            "upstream": "https://github.com/acme/upstream.git",
        },
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-upstream"


def test_project_falls_back_to_origin(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "https://github.com/acme/origin.git"})
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-origin"


def test_invalid_upstream_falls_back_to_origin(fake_home: Path) -> None:
    repo = _git_repo(
        fake_home / "repo",
        {
            "upstream": "file:///srv/local.git",
            "origin": "https://github.com/acme/origin.git",
        },
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-origin"


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/acme/widget.git", "acme-widget"),
        ("git@github.com:acme/widget.git", "acme-widget"),
        ("ssh://git@gitlab.example.com:2222/acme/group/widget.git", "acme-group-widget"),
        ("https://user:token@github.com/acme/widget.git", "acme-widget"),
        ("git@github.com:Acme/Widget.git", "acme-widget"),
        ("git@github.com:Acme/API.git", "acme-api"),
        ("https://gitlab.com/acme/group/api.git", "acme-group-api"),
        # A single-segment owner-only path is still a valid project name.
        ("git@github.com:Acme.git", "acme"),
        # Already-hyphenated path segments are preserved, only ``/`` maps.
        ("git@github.com:acme/acme-widget.git", "acme-acme-widget"),
        ("https://github.com/Acme/Already-Hyphenated.git", "acme-already-hyphenated"),
        # Unusual characters would not produce a valid project name, so the
        # remote is unusable and the basename fallback applies.
        ("https://github.com/acme/weird%20name.git", "repo"),
        ("https://github.com/acme/widget%00.git", "repo"),
    ],
)
def test_remote_url_normalization(fake_home: Path, remote: str, expected: str) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": remote})
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == expected


def test_uppercase_remote_yields_a_server_addressable_project(fake_home: Path) -> None:
    """B1: project names never contain ``/``; case is folded by upstream."""
    repo = _git_repo(fake_home / "repo", {"origin": "git@github.com:Acme/API.git"})
    _marker(repo, 'workspace = "acme"\n')

    scope = resolve_scope(str(repo))

    assert scope["project"] == "acme-api"
    assert "/" not in scope["project"]


def test_nested_group_remote_maps_every_separator(fake_home: Path) -> None:
    repo = _git_repo(
        fake_home / "repo", {"origin": "git@gitlab.com:acme/group/api.git"}
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-group-api"


def test_single_segment_remote_is_a_valid_project_name(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "git@github.com:acme.git"})
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme"


def test_already_hyphenated_remote_stays_hyphenated(fake_home: Path) -> None:
    repo = _git_repo(
        fake_home / "repo", {"origin": "git@github.com:acme/already-hyphenated.git"}
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-already-hyphenated"


@pytest.mark.parametrize("remote", ["file:///srv/local.git", "/srv/local.git", r"C:\local"])
def test_non_remote_urls_use_the_basename(fake_home: Path, remote: str) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": remote})
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "repo"


def test_malformed_ipv6_remote_falls_back_without_crashing(fake_home: Path) -> None:
    """R3: an invalid IPv6 URL must not propagate out of initialization."""
    repo = _git_repo(
        fake_home / "repo", {"origin": "https://[::1/acme/repo.git"}
    )
    _marker(repo, 'workspace = "acme"\n')

    scope = resolve_scope(str(repo))

    assert scope["workspace"] == "acme"
    assert scope["project"] == "repo"
    assert scope["project_source"] == "derived"


def test_malformed_upstream_tries_origin_before_the_basename(fake_home: Path) -> None:
    repo = _git_repo(
        fake_home / "repo",
        {
            "upstream": "https://[::1/acme/upstream.git",
            "origin": "https://github.com/acme/origin.git",
        },
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-origin"


def test_malformed_gitdir_line_falls_back_without_crashing(fake_home: Path) -> None:
    """R3: a NUL in ``gitdir:`` makes ``Path.resolve`` raise ValueError."""
    repo = fake_home / "repo"
    repo.mkdir()
    (repo / ".git").write_bytes(b"gitdir: /tmp/bad\x00dir\n")
    _marker(repo, 'workspace = "acme"\n')

    scope = resolve_scope(str(repo))

    assert scope["workspace"] == "acme"
    assert scope["project"] == "repo"
    assert scope["project_source"] == "derived"


def test_provider_initializes_with_a_malformed_ipv6_remote(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 end to end: ``initialize()`` must not raise on a bad remote."""
    from provider import AiMemoryProvider

    monkeypatch.delenv("AI_MEMORY_CWD", raising=False)
    repo = _git_repo(fake_home / "repo", {"origin": "https://[::1/acme/repo.git"})
    _marker(repo, 'workspace = "acme"\n')

    provider = AiMemoryProvider()
    provider.initialize("session", cwd=str(repo))

    diagnostics = provider.scope_diagnostics()
    assert diagnostics["project"] == "repo"
    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["scope_known"] is True


def test_provider_initializes_with_a_malformed_gitdir(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 end to end: a NUL ``gitdir:`` line must not kill the session."""
    from provider import AiMemoryProvider

    monkeypatch.delenv("AI_MEMORY_CWD", raising=False)
    repo = fake_home / "repo"
    repo.mkdir()
    (repo / ".git").write_bytes(b"gitdir: /tmp/bad\x00dir\n")
    _marker(repo, 'workspace = "acme"\n')

    provider = AiMemoryProvider()
    provider.initialize("session", cwd=str(repo))

    diagnostics = provider.scope_diagnostics()
    assert diagnostics["project"] == "repo"
    assert diagnostics["workspace_source"] == "marker"
    assert diagnostics["scope_known"] is True


def test_git_file_points_at_the_real_config(fake_home: Path) -> None:
    """Worktrees and submodules identify the checkout with a ``.git`` file."""
    repo = fake_home / "repo"
    repo.mkdir()
    git_dir = fake_home / "actual-git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/acme/worktree.git\n',
        encoding="utf-8",
    )
    (repo / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "acme-worktree"


def test_malicious_remote_never_executes_anything(
    fake_home: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "pwned"
    repo = _git_repo(
        fake_home / "repo", {"origin": f"git@evil.example:acme/$(touch {sentinel})"}
    )
    _marker(repo, 'workspace = "acme"\n')

    assert marker_scope(str(repo))["project"] == "repo"
    assert not sentinel.exists()


# ------------------------------------------------------------- resolve_scope


def test_resolve_scope_explicit_beats_marker_and_derivation(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "https://github.com/acme/widget.git"})
    _marker(repo, 'workspace = "marker-ws"\nproject = "marker-project"\n')

    scope = resolve_scope(
        str(repo), explicit_workspace="explicit-ws", explicit_project="explicit-project"
    )

    assert scope["workspace"] == "explicit-ws"
    assert scope["project"] == "explicit-project"
    assert scope["workspace_source"] == "explicit"
    assert scope["project_source"] == "explicit"
    assert scope["source"] == "explicit"


def test_resolve_scope_marker_beats_derivation(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "https://github.com/acme/widget.git"})
    _marker(repo, 'workspace = "acme"\nproject = "pinned"\n')

    scope = resolve_scope(str(repo))

    assert scope["workspace"] == "acme"
    assert scope["project"] == "pinned"
    assert scope["workspace_source"] == "marker"
    assert scope["project_source"] == "marker"


def test_resolve_scope_reports_derived_project(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "https://github.com/acme/widget.git"})
    _marker(repo, 'workspace = "acme"\n')

    scope = resolve_scope(str(repo))

    assert scope["workspace_source"] == "marker"
    assert scope["project"] == "acme-widget"
    assert scope["project_source"] == "derived"
    assert scope["source"] == "derived"


def test_resolve_scope_derives_without_any_marker(fake_home: Path) -> None:
    repo = _git_repo(fake_home / "repo", {"origin": "https://github.com/acme/widget.git"})

    scope = resolve_scope(str(repo))

    assert scope["workspace"] == ""
    assert scope["project"] == "acme-widget"
    assert scope["project_source"] == "derived"


def test_resolve_scope_returns_empty_for_unusable_cwd() -> None:
    assert resolve_scope("") == {}
    assert resolve_scope("/does/not/exist") == {}


# ------------------------------------------------------------ marker boundary


def test_briefing_only_inner_marker_is_a_boundary(fake_home: Path) -> None:
    """The inner marker ends the walk; an outer project must not leak through."""
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    nested = repo / "src"
    _marker(nested, "[briefing]\ninject_on_session_start = true\n")

    assert marker_scope(str(nested)) == {"project": "src"}
    assert marker_briefing(str(nested)) == {
        "inject_on_session_start": "true",
        "max_chars": "",
    }


def test_empty_server_key_is_a_settings_boundary(fake_home: Path) -> None:
    """R2: upstream's ``server_selection_in`` returns Some("") for this key.

    The inner marker must stop the walk even though its value is empty, or the
    outer marker's project would silently capture the inner checkout.
    """
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    nested = _git_repo(
        repo / "inner", {"origin": "git@github.com:acme/inner.git"}
    )
    _marker(nested, 'server = ""\n')

    # The inner checkout falls back to its own identity, never the outer scope.
    assert marker_scope(str(nested)) == {"project": "acme-inner"}
    assert marker_briefing(str(nested)) == {
        "inject_on_session_start": "",
        "max_chars": "",
    }


def test_bare_and_invalid_server_values_are_boundaries(fake_home: Path) -> None:
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    for index, value in enumerate(("server = team-b\n", "server = \"\" # x\n")):
        nested = repo / f"inner{index}"
        _marker(nested, value)
        assert marker_scope(str(nested)) == {"project": f"inner{index}"}


def test_server_url_key_is_not_a_server_boundary(fake_home: Path) -> None:
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    nested = repo / "src"
    _marker(nested, "[capture]\nserver_url = \"https://example.invalid\"\n")

    assert marker_scope(str(nested)) == {
        "workspace": "outer",
        "project": "outer-project",
    }


def test_capture_only_marker_is_transparent(fake_home: Path) -> None:
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    nested = repo / "src"
    _marker(nested, '[capture]\nignore_paths = ["secret/**"]\n')

    assert marker_scope(str(nested)) == {
        "workspace": "outer",
        "project": "outer-project",
    }


def test_routes_only_marker_is_transparent(fake_home: Path) -> None:
    """Upstream's ``declares_more_than_capture`` does not include routes."""
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "outer"\nproject = "outer-project"\n')
    nested = repo / "src"
    _marker(nested, '[routes]\nroute_project = "inner-project"\n')

    assert marker_scope(str(nested)) == {
        "workspace": "outer",
        "project": "outer-project",
    }


# ----------------------------------------------------------------- BOM input


def test_bom_prefixed_workspace_key_parses(fake_home: Path) -> None:
    repo = fake_home / "repo"
    repo.mkdir()
    (repo / ".ai-memory.toml").write_bytes(b'\xef\xbb\xbfworkspace = "bom"\n')

    assert _parse_marker_key('\ufeffworkspace = "bom"\n', "workspace") == "bom"
    assert marker_scope(str(repo)) == {"workspace": "bom", "project": "repo"}


# ------------------------------------------------------------- walk boundary


def test_outside_home_walk_stops_at_the_checkout_root(fake_home: Path) -> None:
    outer = fake_home.parent / "outside"
    repo = outer / "repo"
    (repo / ".git").mkdir(parents=True)
    _marker(outer, 'project = "leaked"\n')
    nested = repo / "sub"
    nested.mkdir()

    assert marker_scope(str(nested)) == {}

    _marker(repo, 'workspace = "inside"\n')
    assert marker_scope(str(nested)) == {"workspace": "inside", "project": "sub"}


def test_outside_home_non_git_directory_checks_only_cwd(fake_home: Path) -> None:
    plain = fake_home.parent / "outside" / "plain"
    nested = plain / "sub"
    nested.mkdir(parents=True)
    _marker(plain, 'project = "parent-marker"\n')

    assert marker_scope(str(nested)) == {}

    _marker(nested, 'project = "cwd-marker"\n')
    assert marker_scope(str(nested)) == {"project": "cwd-marker"}


def test_outside_home_checkout_root_may_be_a_git_file(fake_home: Path) -> None:
    outer = fake_home.parent / "outside"
    repo = outer / "repo"
    repo.mkdir(parents=True)
    # Worktrees/submodules identify the checkout with a file, not a directory.
    (repo / ".git").write_text("gitdir: /nonexistent/worktree\n", encoding="utf-8")
    _marker(outer, 'project = "leaked"\n')
    nested = repo / "sub"
    nested.mkdir()

    assert marker_scope(str(nested)) == {}


def test_inside_home_stops_at_home(fake_home: Path) -> None:
    repo = fake_home / "repo"
    _marker(repo, 'workspace = "acme"\n')
    nested = repo / "src"
    nested.mkdir()

    assert marker_scope(str(nested)) == {"workspace": "acme", "project": "src"}
