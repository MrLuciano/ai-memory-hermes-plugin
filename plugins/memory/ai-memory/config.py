from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

log = logging.getLogger(__name__)

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

DEFAULT_SERVER_URL = "http://127.0.0.1:49374"

# Env vars the plugin honours; each one overrides the JSON file below it.
_ENV_MAP: dict[str, str] = {
    "AI_MEMORY_SERVER_URL": "server_url",
    "AI_MEMORY_AUTH_TOKEN": "auth_token",
    "AI_MEMORY_API_KEY": "api_key",
    "AI_MEMORY_WORKSPACE": "workspace",
    "AI_MEMORY_PROJECT": "project",
    "AI_MEMORY_SEARCH_SCOPE": "search_scope",
}

# Scope keys ``.ai-memory.toml`` may pin, in the server's own order.
_MARKER_SCOPE_KEYS: tuple[str, ...] = ("workspace", "project")
_MARKER_FILENAME = ".ai-memory.toml"


@dataclass
class AiMemoryConfig:
    server_url: str = DEFAULT_SERVER_URL
    api_key: str = ""
    auth_token: str = ""
    workspace: str = "hermes"
    project: str = "hermes-default"
    search_scope: str = "global"

    def __post_init__(self) -> None:
        _validate_search_scope(self.search_scope)


def _validate_search_scope(value: Any) -> None:
    if value not in ("global", "project"):
        raise ValueError("search_scope must be global or project")


def _validate_scope_origin(values: dict[str, Any]) -> None:
    if "scope_origin" in values and values["scope_origin"] not in ("automatic", "explicit"):
        raise ValueError("scope_origin must be automatic or explicit")


def get_config_schema() -> list[dict[str, Any]]:
    return [
        {
            "key": "server_url",
            "description": "ai-memory server URL",
            "default": DEFAULT_SERVER_URL,
            "required": False,
        },
        {
            "key": "api_key",
            "description": "ai-memory API key (optional for local mode)",
            "secret": True,
            "env_only": True,
            "required": False,
            "env_var": "AI_MEMORY_API_KEY",
        },
        {
            "key": "auth_token",
            "description": "ai-memory auth token (optional for local mode)",
            "secret": True,
            "env_only": True,
            "required": False,
            "env_var": "AI_MEMORY_AUTH_TOKEN",
        },
        {
            "key": "search_scope",
            "description": "Recall scope: global (legacy default) or project",
            "default": "global",
            "choices": ["global", "project"],
            "required": False,
        },
        {
            "key": "workspace",
            "description": "Workspace override (blank uses the directory marker)",
            "default": "",
            "required": False,
        },
        {
            "key": "project",
            "description": "Project override (blank uses the directory marker)",
            "default": "",
            "required": False,
        },
    ]


def _secret_keys() -> dict[str, str]:
    """Return {config_key: env_var_name} for all secret/env-only fields."""
    schema = get_config_schema()
    result: dict[str, str] = {}
    for item in schema:
        if item.get("secret"):
            env_var = item.get("env_var", f"AI_MEMORY_{item['key'].upper()}")
            result[item["key"]] = env_var
    return result


def save_config(values: dict[str, Any], hermes_home: str) -> list[str]:
    """Save non-secret config values to disk. Returns list of skipped secret keys."""
    if "search_scope" in values:
        _validate_search_scope(values["search_scope"])
    _validate_scope_origin(values)
    secrets = _secret_keys()
    skipped: list[str] = []
    safe_values: dict[str, Any] = {}
    for k, v in values.items():
        if k in secrets:
            log.info("secret %s not written to disk — set %s instead", k, secrets[k])
            skipped.append(k)
            continue
        safe_values[k] = v

    p = Path(hermes_home) / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    # Also strip any secrets already persisted in the file
    for secret_key in secrets:
        existing.pop(secret_key, None)

    existing.update(safe_values)
    for key in _MARKER_SCOPE_KEYS:
        if key in safe_values and not str(safe_values[key]).strip():
            existing.pop(key, None)
    if "scope_origin" not in safe_values and any(
        str(safe_values.get(key, "")).strip() for key in _MARKER_SCOPE_KEYS
    ):
        existing["scope_origin"] = "explicit"
    p.write_text(json.dumps(existing, indent=2))
    return skipped


def _read_overrides(hermes_home: str) -> dict[str, Any]:
    """JSON-file overrides, then env-var overrides (env wins)."""
    overrides: dict[str, Any] = {}
    p = Path(hermes_home) / "ai-memory.json" if hermes_home else None

    if p is not None and p.exists():
        try:
            overrides = json.loads(p.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            overrides = {}

    _validate_scope_origin(overrides)
    # Only the complete legacy-generated shape is ambiguous. Never infer
    # provenance from a project name alone or reinterpret customized files.
    effective_mode = os.environ.get("AI_MEMORY_SEARCH_SCOPE") or overrides.get(
        "search_scope", "global"
    )
    legacy_keys = {"server_url", "workspace", "project", "search_scope", "scope_origin"}
    if (
        effective_mode == "project"
        and overrides.get("scope_origin") != "explicit"
        and set(overrides) <= legacy_keys
        and overrides.get("workspace") == "hermes"
        and overrides.get("project") == "hermes-default"
    ):
        overrides.pop("workspace")
        overrides.pop("project")

    for env_key, attr in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if val:
            overrides[attr] = val

    return overrides


def explicit_scope_keys(hermes_home: str) -> set[str]:
    """Scope keys the operator set explicitly (file or env), never defaults.

    ``initialize()`` must know whether ``workspace``/``project`` came from the
    operator or from ``AiMemoryConfig``'s defaults: an explicit value beats the
    ``.ai-memory.toml`` marker, a default loses to it.
    """
    overrides = _read_overrides(hermes_home)
    return {key for key in _MARKER_SCOPE_KEYS if str(overrides.get(key, "")).strip()}


def _parse_marker_key(text: str, key: str) -> str:
    """Line-based ``key = "value"`` reader, mirroring ai-memory's parser.

    Section headers are ignored and only double-quoted values are accepted, so
    the plugin resolves the same marker text the server and the shell hooks do.
    """
    for line in text.splitlines():
        # A BOM is not whitespace to ``lstrip``, and would hide a first-line key.
        trimmed = line.lstrip("\ufeff").lstrip()
        if not trimmed.startswith(key):
            continue
        rest = trimmed[len(key) :].lstrip()
        if not rest.startswith("="):
            continue
        rest = rest[1:].lstrip()
        if not rest.startswith('"'):
            continue
        end = rest[1:].find('"')
        if end < 0:
            continue
        return rest[1 : end + 1]
    return ""


def _parse_marker_flag(text: str, key: str) -> str:
    """Line-based ``key = true`` reader, accepting quoted or bare values.

    Mirrors ai-memory's ``parse_flag_in``: section headers are ignored, the
    first match wins, an optional trailing ``# comment`` is stripped, and the
    surrounding double quotes are removed. Used for ``[briefing]`` and the
    other section-style flags, which the strict key reader above rejects.
    """
    for line in text.splitlines():
        trimmed = line.lstrip("\ufeff").lstrip()
        if not trimmed.startswith(key):
            continue
        rest = trimmed[len(key) :].lstrip()
        if not rest.startswith("="):
            continue
        value = rest[1:].split("#", 1)[0].strip().strip('"')
        if value:
            return value
    return ""


_MARKER_QUOTED_SETTINGS: tuple[str, ...] = (
    "workspace",
    "project",
    "project_strategy",
    "drop_subagent_captures",
    "identity",
    "identity_style",
)
_MARKER_FLAG_SETTINGS: tuple[str, ...] = (
    "default_global",
    "inject_on_session_start",
    "max_chars",
    "contribute",
    "consume",
)


def _marker_declares_server(text: str) -> bool:
    """Whether *text* contains a ``server`` key, whatever its value.

    Mirrors ai-memory's ``server_selection_in``: the key's *presence* is a
    settings boundary. An empty ``server = ""`` still counts (and is later
    rejected by profile-name validation), so the walk must stop here rather
    than inherit an outer marker's scope and route the inner checkout there.
    """
    for line in text.splitlines():
        trimmed = line.lstrip("\ufeff").lstrip()
        if not trimmed.startswith("server"):
            continue
        rest = trimmed[len("server") :].lstrip()
        if rest.startswith("="):
            return True
    return False


def _marker_declares_settings(text: str) -> bool:
    """Whether a marker declares anything beyond a ``[capture]`` section.

    Mirrors ai-memory's ``declares_more_than_capture``: only a marker whose
    sole content is ``[capture]`` is transparent to the settings walk. The
    check is deliberately conservative - a stray key anywhere turns a marker
    into a boundary, never the other way round.
    """
    if any(_parse_marker_key(text, key) for key in _MARKER_QUOTED_SETTINGS):
        return True
    if any(_parse_marker_flag(text, key) for key in _MARKER_FLAG_SETTINGS):
        return True
    if _marker_declares_server(text):
        return True
    for line in text.splitlines():
        trimmed = line.lstrip("\ufeff").lstrip()
        if trimmed.startswith("aliases") and trimmed[len("aliases") :].lstrip().startswith("="):
            return True
    return False


def validated_directory(cwd: str) -> Path | None:
    """Native absolute existing directory, never anchored to the process cwd.

    MSYS spellings are deliberately not translated here: the host's --in
    already translates them, but must still pass its session cwd to providers.
    """
    if not cwd:
        return None
    try:
        directory = Path(cwd).expanduser()
        if directory.is_absolute() and directory.is_dir():
            return directory
    except (OSError, ValueError):
        pass
    return None


def marker_scope(cwd: str) -> dict[str, str]:
    """``workspace``/``project`` for *cwd*, derived the way upstream does.

    The walk stops at the nearest *settings boundary* - a marker that declares
    more than a ``[capture]`` section - and reads scope only from that marker.
    A capture-only marker is transparent. When the boundary pins ``workspace``
    but not ``project``, the project is derived from the checkout's git remote
    (``upstream``, else ``origin``) or, without a valid remote, from
    ``basename(cwd)``. Returns ``{}`` when *cwd* is unusable or no settings
    marker exists.
    """
    directory = validated_directory(cwd)
    if directory is None:
        return {}

    found, scope = _marker_pinned_scope(directory)
    if not found:
        return {}
    if "project" not in scope:
        derived = _derive_project(directory)
        if derived:
            scope["project"] = derived
    return scope


def marker_briefing(cwd: str) -> dict[str, str]:
    """``[briefing]`` flags declared by the nearest settings marker.

    Walks up from *cwd* like the hook clients: a marker whose only content is
    ``[capture]`` is transparent and the walk continues, while the first
    marker that declares any setting is the resolution boundary - even when
    it does not opt into the brief, so an outer marker cannot leak through.
    Returns ``{}`` when *cwd* is empty or no settings marker exists.
    """
    directory = validated_directory(cwd)
    if directory is None:
        return {}

    found = _find_settings_marker(directory)
    if found is None:
        return {}
    text = found[1]
    return {
        "inject_on_session_start": _parse_marker_flag(text, "inject_on_session_start"),
        "max_chars": _parse_marker_flag(text, "max_chars"),
    }


def resolve_scope(
    cwd: str, *, explicit_workspace: str = "", explicit_project: str = ""
) -> dict[str, str]:
    """Resolve the effective ai-memory scope the way upstream hook clients do.

    Precedence: explicit config/kwargs > marker (at the nearest settings
    boundary) > derivation (git remote, else ``basename(cwd)``).

    Returns a mapping with ``workspace`` and ``project`` (empty when nothing
    resolved the field), ``workspace_source``/``project_source`` (``explicit``,
    ``marker``, ``derived``, or empty), and ``source`` - the project's source
    when a project resolved, else the workspace's. Returns ``{}`` when *cwd*
    is unusable.

    A derived project is *not* operator-pinned: callers that need to tell an
    operator's choice from a repository-derived one must inspect
    ``project_source``.
    """
    directory = validated_directory(cwd)
    if directory is None:
        return {}

    _, pinned = _marker_pinned_scope(directory)

    workspace = explicit_workspace.strip()
    if workspace:
        workspace_source = "explicit"
    elif pinned.get("workspace"):
        workspace = pinned["workspace"]
        workspace_source = "marker"
    else:
        workspace = ""
        workspace_source = ""

    project = explicit_project.strip()
    if project:
        project_source = "explicit"
    elif pinned.get("project"):
        project = pinned["project"]
        project_source = "marker"
    else:
        project = _derive_project(directory)
        project_source = "derived" if project else ""

    return {
        "workspace": workspace,
        "project": project,
        "workspace_source": workspace_source,
        "project_source": project_source,
        "source": project_source or workspace_source,
    }


def _read_marker_text(path: Path) -> str:
    """Marker text as UTF-8; a leading BOM is tolerated, an unreadable file is empty."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def _checkout_root(start: Path) -> Path | None:
    """Nearest ancestor holding a ``.git`` entry (directory *or* file)."""
    for directory in (start, *start.parents):
        try:
            if (directory / ".git").exists():
                return directory
        except OSError:
            continue
    return None


def _marker_walk_boundary(start: Path) -> Path:
    """Where a marker walk from *start* must stop.

    Inside ``$HOME``: ``$HOME``. Outside it: the nearest checkout root, or
    *start* itself when it lies in no checkout (so only ``cwd`` is checked).
    """
    home = Path.home().absolute()
    if start.is_relative_to(home):
        return home
    return _checkout_root(start) or start


def _find_settings_marker(start: Path) -> tuple[Path, str] | None:
    """First marker on the walk that declares more than ``[capture]``."""
    boundary = _marker_walk_boundary(start)
    directory = start
    while True:
        candidate = directory / _MARKER_FILENAME
        try:
            is_file = candidate.is_file()
        except OSError:
            is_file = False
        if is_file:
            text = _read_marker_text(candidate)
            if _marker_declares_settings(text):
                return candidate, text
        if directory == boundary or directory.parent == directory:
            return None
        directory = directory.parent


def _marker_pinned_scope(start: Path) -> tuple[bool, dict[str, str]]:
    """Whether a settings marker exists, and the scope keys it *pins*.

    Pinned values only, so callers can distinguish an operator's marker from a
    derived fallback. A boundary marker that pins no scope key returns
    ``(True, {})``; no settings marker returns ``(False, {})``.
    """
    found = _find_settings_marker(start)
    if found is None:
        return False, {}
    text = found[1]
    return True, {
        key: value for key in _MARKER_SCOPE_KEYS if (value := _parse_marker_key(text, key))
    }


_REMOTE_SECTION = re.compile(
    r'^remote(?:\s*\.\s*(?P<dotted>[^\s"]+)|\s+"(?P<quoted>[^"]*)")\s*$', re.IGNORECASE
)


def _git_config_path(start: Path) -> Path | None:
    """The nearest checkout's ``.git/config`` (handles worktree/submodule files)."""
    for directory in (start, *start.parents):
        dotgit = directory / ".git"
        try:
            if dotgit.is_dir():
                return dotgit / "config"
            if dotgit.is_file():
                return _git_file_config_path(dotgit, directory)
        except OSError:
            continue
    return None


def _git_file_config_path(dotgit: Path, owner: Path) -> Path | None:
    try:
        text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.lower().startswith("gitdir:"):
        return None
    raw = text.split(":", 1)[1].strip()
    if not raw:
        return None
    gitdir = Path(raw)
    if not gitdir.is_absolute():
        gitdir = owner / gitdir
    try:
        gitdir = gitdir.resolve()
    except (OSError, ValueError):
        # A ``gitdir:`` line carrying a NUL (or another invalid component)
        # makes ``Path.resolve`` raise ValueError; an unusable checkout must
        # not crash initialization.
        return None
    config = gitdir / "config"
    if config.is_file():
        return config
    try:
        common = (gitdir / "commondir").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return config
    if not common:
        return config
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = gitdir / common_dir
    try:
        return common_dir.resolve() / "config"
    except (OSError, ValueError):
        return config


def _parse_git_config_remotes(text: str) -> dict[str, str]:
    """``{remote_name: url}`` from ``.git/config`` text, last value winning."""
    remotes: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("["):
            end = stripped.find("]")
            if end < 0:
                current = None
                continue
            match = _REMOTE_SECTION.match(stripped[1:end].strip())
            current = (
                (match.group("dotted") or match.group("quoted")) if match is not None else None
            )
            continue
        if current is None or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().lower() != "url":
            continue
        value = value.strip()
        if value.startswith('"'):
            end = value.find('"', 1)
            value = value[1:end] if end >= 0 else value[1:]
        else:
            for marker in (" #", "\t#", " ;", "\t;"):
                index = value.find(marker)
                if index >= 0:
                    value = value[:index]
            value = value.strip()
        if value:
            remotes[current] = value
    return remotes


# ai-memory project names never contain ``/``: upstream's ``path`` identity
# style names a repository from its hostless path with ``/`` written as ``-``
# (``github.com/acme/api`` -> ``acme-api``). The server stores names verbatim,
# but its documented safe shape is lowercase ASCII plus ``.``/``_``/``-``.
_DERIVED_PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _normalize_remote_project(url: str) -> str:
    """Canonical ai-memory project name from a git remote URL, or ``""``.

    Mirrors upstream's ``identity_style = "path"`` naming: the hostless
    repository path, lowercased, with ``/`` written as ``-`` and a trailing
    ``.git`` removed. ``git@github.com:Acme/API.git`` therefore becomes
    ``acme-api``, never ``Acme/API`` - project names never contain ``/``.
    Parsing is purely lexical: no remote value is ever passed to a shell.

    A path that would not yield a valid project name (whitespace, control
    characters, leading punctuation) is treated as unusable so callers fall
    back to the next remote or ``basename(cwd)``. A malformed URL is
    likewise unusable rather than fatal: ``urlsplit`` raises ``ValueError``
    for inputs such as an unterminated IPv6 host.
    """
    raw = url.strip()
    if not raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return ""

    if "://" in raw:
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return ""
        if parsed.scheme.lower() == "file" or not parsed.netloc:
            return ""
        path = unquote(parsed.path)
    else:
        # scp-like ``[user@]host:path``. A backslash or a one-character host
        # is a local Windows path, not a remote.
        if "\\" in raw or ":" not in raw:
            return ""
        host, path = raw.split(":", 1)
        host = host.rsplit("@", 1)[-1]
        if len(host) <= 1 or "/" in host:
            return ""

    path = path.replace("\\", "/").strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    path = path.strip("/")
    if not path:
        return ""

    segments = path.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        return ""
    if any(char.isspace() or ord(char) < 32 for segment in segments for char in segment):
        return ""

    name = "-".join(segment.lower() for segment in segments)
    if _DERIVED_PROJECT_NAME.fullmatch(name) is None:
        return ""
    return name


def _discover_remote_project(start: Path) -> str:
    """Project from the checkout's ``upstream`` remote, else ``origin``."""
    config = _git_config_path(start)
    if config is None:
        return ""
    try:
        if not config.is_file():
            return ""
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    remotes = _parse_git_config_remotes(text)
    for name in ("upstream", "origin"):
        project = _normalize_remote_project(remotes.get(name, ""))
        if project:
            return project
    return ""


def _derive_project(start: Path) -> str:
    """Upstream derivation: git remote path, else ``basename(cwd)``."""
    return _discover_remote_project(start) or start.name


def load_config(hermes_home: str, base: AiMemoryConfig | None = None) -> AiMemoryConfig:
    """Apply file/env overrides to defaults or an unscoped programmatic base."""
    overrides = _read_overrides(hermes_home)
    return replace(
        base or AiMemoryConfig(),
        **{k: v for k, v in overrides.items() if hasattr(AiMemoryConfig, k)},
    )
