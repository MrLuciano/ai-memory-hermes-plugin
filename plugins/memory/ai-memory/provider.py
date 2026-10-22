from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from client import SESSION_END_TIMEOUT, AiMemoryClient  # noqa: E402
from config import (  # noqa: E402
    AiMemoryConfig,
    explicit_scope_keys,
    get_config_schema,
    load_config,
    resolve_scope,
    save_config,
    validated_directory,
)

try:
    from agent.memory_provider import MemoryProvider, RecallStatus  # type: ignore[import-untyped]
except ImportError:
    from abc import ABC as _ABC
    from dataclasses import dataclass as _dataclass

    class MemoryProvider(_ABC):  # type: ignore[no-redef]
        pass

    @_dataclass(frozen=True)
    class RecallStatus:  # type: ignore[no-redef]
        """Standalone fallback mirroring Hermes' ``RecallStatus``."""

        provider_label: str
        count: int
        glyph: str = "🧠"


log = logging.getLogger(__name__)

# Recall hits injected per prefetch, and how many sessions' results the
# background cache holds before the oldest is evicted.
_PREFETCH_RESULTS = 3
_PREFETCH_CACHE_MAX = 8

# Bounded drain for our own background workers at shutdown. Hermes' own drain
# is bounded at 5s (_SYNC_DRAIN_TIMEOUT_S, agent/memory_manager.py:41) and only
# covers its executor (_drain_sync_executor, agent/memory_manager.py:870-905);
# it cannot see the threads this provider spawns, so shutdown() joins them here.
_SHUTDOWN_JOIN_TIMEOUT = 5.0
# The session-end POST is issued with the client's longer SESSION_END_TIMEOUT
# budget. It must not share the generic 5s slice: shutdown() historically
# returned while that daemon worker was still in flight and the session close
# (plus its auto-handoff) was lost at interpreter exit.
_SESSION_END_JOIN_TIMEOUT = SESSION_END_TIMEOUT
# Hard cap for a single shutdown() call: the longest worker budget plus a
# generic slice for any other workers still in flight.
_MAX_SHUTDOWN_JOIN_TIMEOUT = _SESSION_END_JOIN_TIMEOUT + _SHUTDOWN_JOIN_TIMEOUT


@dataclass(frozen=True)
class _TrackedWorker:
    """A started background worker and the time its in-flight call may need."""

    thread: threading.Thread
    join_budget: float


@dataclass(frozen=True)
class _OperationContext:
    client: AiMemoryClient
    session_id: str
    workspace: str
    project: str
    cwd: str
    search_scope: str
    generation: int
    scope_known: bool
    writes_enabled: bool

    def cache_key(self, query: str) -> tuple[str, str, str, str, str]:
        return (self.session_id, self.search_scope, self.workspace, self.project, query)

    def search_params(self) -> dict[str, str]:
        if self.search_scope == "global":
            return {}
        return {"workspace": self.workspace, "project": self.project}


class AiMemoryProvider(MemoryProvider):
    def __init__(
        self,
        client: AiMemoryClient | None = None,
        config: AiMemoryConfig | None = None,
    ) -> None:
        self._config = replace(config) if config is not None else AiMemoryConfig()
        self._configured_config: AiMemoryConfig | None = None
        _default_config = AiMemoryConfig()
        self._workspace_source = (
            "explicit"
            if self._config.workspace.strip()
            and self._config.workspace != _default_config.workspace
            else ""
        )
        self._project_source = (
            "explicit"
            if self._config.project.strip()
            and self._config.project != _default_config.project
            else ""
        )
        self._scope_known = self._scope_authorized(
            self._config.workspace,
            self._config.project,
            self._workspace_source,
            self._project_source,
        )
        self._client = client or AiMemoryClient(self._config)
        self._lock = threading.RLock()
        self._generation = 0
        self.session_id: str = ""
        self._hermes_home: str = ""
        self._cwd: str = ""
        self._cwd_normalized: str = ""
        self._cwd_source: str = ""
        # Non-primary contexts (subagent / cron / flush) get no writes and must
        # not consume the single-use handoff. The default keeps standalone
        # callers writing, since only Hermes reports a context.
        self._agent_context: str = "primary"
        self._writes_enabled: bool = True
        # Background recall from queue_prefetch, consumed once by prefetch.
        # ``_prefetch_cache`` is keyed by the exact query; ``_prefetch_latest``
        # is keyed by session+scope and remembers the newest queued recall, which
        # is what Hermes actually consumes (it queues with the completed turn's
        # user text and prefetches with the next turn's text).
        self._prefetch_cache: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
        self._prefetch_latest: dict[
            tuple[str, str, str, str], tuple[str, list[dict[str, Any]]]
        ] = {}
        self._last_recall_count: int = 0
        # Previous-session handoff, fetched once per session in initialize()
        # and surfaced through system_prompt_block(). None = none pending.
        self._handoff_context: str | None = None
        # Threads spawned for background work, joined (bounded) in shutdown().
        self._worker_threads: list[_TrackedWorker] = []
        # Once shutdown starts, a late spawn must not create an untracked daemon
        # that outlives the join. Such work runs inline instead.
        self._shutting_down = False

    @property
    def name(self) -> str:
        return "ai-memory"

    def is_available(self) -> bool:
        # ai-memory does not require authentication by default; the provider
        # is available whenever a server URL is configured.
        return bool(self._config.server_url)

    def unavailable_reason(self) -> str:
        """Why the provider cannot serve: no URL, or a recorded transport failure."""
        if not self._config.server_url:
            return "AI_MEMORY_SERVER_URL is not configured"
        failure = self._client.last_failure()
        return f"ai-memory server unreachable ({failure})" if failure else ""

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        hermes_home = kwargs.get("hermes_home", "")
        with self._lock:
            self.session_id = session_id
            self._hermes_home = hermes_home
            # Non-primary contexts must not write or consume a handoff.
            self._agent_context = str(kwargs.get("agent_context") or "primary")
            self._writes_enabled = self._agent_context in ("", "primary")
            cwd, cwd_source = self._resolve_cwd(kwargs)
            self._cwd = cwd
            self._cwd_source = cwd_source
            directory = validated_directory(cwd)
            self._cwd_normalized = str(directory) if directory is not None else ""
            self._generation += 1
            self._handoff_context = None
            self._scope_known = False
            self._workspace_source = ""
            self._project_source = ""
            self._prefetch_cache.clear()
            self._prefetch_latest.clear()
            self._last_recall_count = 0
            if self._configured_config is None:
                self._configured_config = replace(self._config)
            self._config = load_config(
                hermes_home, base=self._configured_config if not hermes_home else None
            )

            server_url = kwargs.get("ai_memory_server_url", "")
            if server_url:
                self._config.server_url = server_url

            auth_token = kwargs.get("ai_memory_auth_token", "")
            if auth_token:
                self._config.auth_token = auth_token

            self._resolve_scope(kwargs, hermes_home)
            diagnostics = self.scope_diagnostics()
            log.info(
                "ai-memory scope: cwd_received=%r cwd_source=%r cwd_normalized=%r "
                "search_scope=%r workspace=%r project=%r workspace_source=%r "
                "project_source=%r scope_known=%r writes_allowed=%r "
                "project_search_allowed=%r",
                diagnostics["cwd_received"], diagnostics["cwd_source"],
                diagnostics["cwd_normalized"], diagnostics["search_scope"],
                diagnostics["workspace"], diagnostics["project"],
                diagnostics["workspace_source"], diagnostics["project_source"],
                diagnostics["scope_known"], diagnostics["writes_allowed"],
                diagnostics["project_search_allowed"],
            )

            self._client = AiMemoryClient(self._config)
            context = self._snapshot()

        # One handoff fetch per session, never polled. Loopback server plus
        # a 2s timeout, so a synchronous call cannot hold up startup, and
        # any failure leaves the provider working without a handoff.
        if not self._has_write_scope(context):
            return
        try:
            handoff = context.client.fetch_handoff(
                agent="hermes",
                cwd=context.cwd,
                workspace=context.workspace,
                project=context.project,
            )
            with self._lock:
                if context.generation == self._generation:
                    self._handoff_context = handoff
        except Exception:
            log.warning("ai-memory handoff fetch failed", exc_info=True)

    def _resolve_cwd(self, kwargs: dict[str, Any]) -> tuple[str, str]:
        """The session working directory and where it came from.

        Hermes only adds ``cwd`` to the init kwargs when ``agent.session_cwd``
        is truthy (agent/agent_init.py:1294-1295); the interactive CLI builds
        ``AIAgent`` without it (hermes_cli/cli_agent_setup_mixin.py:695-744),
        so ``cwd`` is normally absent on ``hermes chat``. Follow upstream's
        guidance (website/docs/developer-guide/memory-provider-plugin.md:
        134-139) and ask ``agent.runtime_cwd.resolve_agent_cwd()``, guarded so
        the plugin still loads without Hermes. An explicit ``AI_MEMORY_CWD``
        wins over both; an invalid explicit value fails closed rather than
        silently falling through to a different directory.
        """
        env_cwd = os.environ.get("AI_MEMORY_CWD", "").strip()
        if env_cwd:
            return env_cwd, "environment"
        kwarg_cwd = str(kwargs.get("cwd") or "").strip()
        if kwarg_cwd:
            return kwarg_cwd, "kwargs"
        try:
            from agent.runtime_cwd import resolve_agent_cwd  # type: ignore[import-untyped]
        except Exception:
            return "", ""
        try:
            resolved = resolve_agent_cwd()
        except Exception:
            log.debug("ai-memory: resolve_agent_cwd() failed", exc_info=True)
            return "", ""
        return (str(resolved) if resolved else ""), "runtime"

    def _resolve_scope(self, kwargs: dict[str, Any], hermes_home: str) -> None:
        """Resolve this session's ``workspace``/``project`` and its provenance.

        Delegates marker and derivation logic to ``config.resolve_scope``
        instead of re-implementing it. Precedence: explicit operator values
        (the ``ai_memory_workspace``/``project`` kwargs, an ``AI_MEMORY_*`` env
        var, or a non-default programmatic config) > the nearest settings
        marker > a project derived from the git remote or ``basename(cwd)``.
        """
        explicit_keys = explicit_scope_keys(hermes_home)
        default = AiMemoryConfig()
        base = self._configured_config if not hermes_home else None

        explicit_workspace = str(kwargs.get("ai_memory_workspace") or "")
        if not explicit_workspace and "workspace" in explicit_keys:
            explicit_workspace = self._config.workspace

        explicit_project = str(kwargs.get("project") or "")
        if not explicit_project and "project" in explicit_keys:
            explicit_project = self._config.project

        programmatic_project = bool(
            base is not None
            and base.project
            and base.project != default.project
            and self._config.project == base.project
        )

        resolved = resolve_scope(
            self._cwd,
            explicit_workspace=explicit_workspace,
            explicit_project=explicit_project,
        )
        # resolve_scope() returns {} for an unusable cwd, so explicit values
        # still have to be applied here: an operator may pin scope without a
        # working directory (the documented CLI path omits cwd).
        workspace = resolved.get("workspace", "")
        project = resolved.get("project", "")
        workspace_source = resolved.get("workspace_source", "")
        project_source = resolved.get("project_source", "")

        # A non-default programmatic config is an operator choice. It must not
        # outrank a marker (legacy behaviour), but it does outrank a project
        # merely derived from a git remote / directory name.
        if project_source == "derived" and programmatic_project:
            project = self._config.project
            project_source = "explicit"

        if not workspace:
            # An explicit value survives an unusable cwd (resolve_scope
            # returns {} then); it is an operator pin, not a derivation.
            workspace = explicit_workspace
        if not workspace:
            # agent_workspace is the literal "hermes", not a path: use it only
            # as a value, never as provenance.
            workspace = str(kwargs.get("agent_workspace") or "")
        if not workspace:
            workspace = self._config.workspace
        if not workspace_source and explicit_workspace:
            workspace_source = "explicit"
        elif (
            not workspace_source
            and base is not None
            and base.workspace
            and base.workspace != default.workspace
            and self._config.workspace == base.workspace
        ):
            # A non-default programmatic config is an operator choice too, but
            # it must not outrank a marker above; it only fills a gap.
            workspace_source = "explicit"
        if workspace:
            self._config.workspace = workspace

        if not project and explicit_project:
            project = explicit_project
            project_source = "explicit"
        if not project:
            project = self._config.project
            if (
                base is not None
                and base.project
                and base.project != default.project
                and self._config.project == base.project
            ):
                project_source = "explicit"
            else:
                project_source = ""
        if not project:
            identity = kwargs.get("agent_identity", "") or "default"
            project = f"hermes-{identity}"
            project_source = ""
        self._config.project = project

        self._workspace_source = workspace_source
        self._project_source = project_source
        self._scope_known = self._scope_authorized(
            workspace, project, workspace_source, project_source
        )

    @staticmethod
    def _scope_authorized(
        workspace: str, project: str, workspace_source: str, project_source: str
    ) -> bool:
        """Whether this scope may authorize project-scoped reads and writes.

        Both fields must be non-empty. The project must be operator-pinned
        (``explicit``/``marker``) or derived from a workspace that is itself
        explicit/marker (upstream's workspace-only marker shape). A project
        that is only the dataclass default, or only derived from an unmarked
        directory, has no provenance and stays fail-closed.
        """
        if not workspace.strip() or not project.strip():
            return False
        if project_source in ("explicit", "marker"):
            return True
        return project_source == "derived" and workspace_source in ("explicit", "marker")

    def scope_diagnostics(self) -> dict[str, Any]:
        """Allowlisted local state only: no network, secrets, or memory content.

        Read the current instance, not a new provider or process cwd. An empty
        normalized path means the received cwd was absent or invalid; an empty
        ``cwd_source`` means nothing resolved. Scope provenance distinguishes
        an operator-pinned project from one derived for a workspace-only
        marker.
        """
        with self._lock:
            context = self._snapshot()
            return {
                "cwd_received": self._cwd,
                "cwd_source": self._cwd_source,
                "cwd_normalized": self._cwd_normalized,
                "search_scope": context.search_scope,
                "workspace": context.workspace,
                "project": context.project,
                "workspace_source": self._workspace_source,
                "project_source": self._project_source,
                "scope_known": context.scope_known,
                "writes_allowed": self._has_write_scope(context),
                "project_search_allowed": context.scope_known,
            }

    def _snapshot(self, session_id: str = "") -> _OperationContext:
        with self._lock:
            return _OperationContext(
                client=self._client,
                session_id=session_id or self.session_id,
                workspace=self._config.workspace,
                project=self._config.project,
                cwd=self._cwd,
                search_scope=self._config.search_scope,
                generation=self._generation,
                scope_known=bool(
                    self._scope_known and self._config.workspace.strip()
                    and self._config.project.strip()
                ),
                writes_enabled=self._writes_enabled,
            )

    def _has_write_scope(self, context: _OperationContext | None = None) -> bool:
        context = context or self._snapshot()
        return context.writes_enabled and context.scope_known

    def get_config_schema(self) -> list[dict[str, Any]]:
        return get_config_schema()

    def save_config(self, values: dict[str, Any], hermes_home: str) -> list[str]:
        return save_config(values, hermes_home)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "ai_memory_search",
                "description": "Search the ai-memory wiki for relevant context",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "ai_memory_write",
                "description": "Write a new page to the ai-memory wiki",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Wiki page path"},
                        "body": {"type": "string", "description": "Markdown body"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["path", "body"],
                },
            },
            {
                "name": "ai_memory_status",
                "description": "Check ai-memory server health",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        if tool_name == "ai_memory_search":
            return json.dumps(self._search(args))
        if tool_name == "ai_memory_write":
            return json.dumps(self._write(args))
        if tool_name == "ai_memory_status":
            return json.dumps(self._status())
        raise ValueError(f"Unknown tool: {tool_name}")

    _BASE_PROMPT = "Long-term memory is backed by ai-memory wiki."

    def system_prompt_block(self) -> str:
        if not self._handoff_context:
            return self._BASE_PROMPT
        return self._BASE_PROMPT + "\n\nPrevious session handoff:\n" + self._handoff_context

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Consume queued recall for this session, or search synchronously.

        Hermes queues with the *completed* turn's user text and prefetches with
        the *next* turn's text, so an exact-query hit is the exception. The
        newest queued entry for the same session/scope is therefore consumed
        even when the query text changed; the exact-query alias is consumed
        first when it exists.
        """
        context = self._snapshot(session_id)
        scope_key = context.cache_key(query)[:4]
        with self._lock:
            hits = self._prefetch_cache.pop(context.cache_key(query), None)
            latest = self._prefetch_latest.get(scope_key)
            if hits is None and latest is not None:
                queued_query, hits = self._prefetch_latest.pop(scope_key)
                self._prefetch_cache.pop(context.cache_key(queued_query), None)
            elif latest is not None and latest[0] == query:
                self._prefetch_latest.pop(scope_key, None)
        if hits is None:
            results = self._search(
                {"query": query, "max_results": _PREFETCH_RESULTS}, context=context
            )
            hits = results.get("results", []) if isinstance(results, dict) else []
        with self._lock:
            if context.generation != self._generation:
                return ""
            self._last_recall_count = len(hits)
        return self._format_recall(hits)

    @staticmethod
    def _format_recall(hits: list[dict[str, Any]]) -> str:
        """One block per hit, labelled with its page path when the server sends one.

        Global is the legacy default; project mode restricts the search.
        Both modes label recalled facts with their source page.
        """
        lines: list[str] = []
        for hit in hits:
            snippet = str(hit.get("snippet", ""))
            title = str(hit.get("title", ""))
            path = str(hit.get("path", ""))
            label = f"{title} ({path})" if title and path else (path or title)
            lines.append(f"{label}: {snippet}" if label else snippet)
        return "\n\n".join(lines)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Recall in the background for the next turn.

        Hermes calls this after each turn with that turn's ``session_id`` and
        user text, but the following ``prefetch()`` receives the *new* turn's
        text. Results are therefore cached both under the exact query and as
        the newest entry for session+scope, which ``prefetch()`` consumes next
        turn even if the text changed. Scope and client are captured before
        dispatch; stale workers cannot repopulate the cache after
        initialization or a session switch.
        """
        if not query:
            return
        context = self._snapshot(session_id)
        if context.search_scope == "project" and not context.scope_known:
            return
        key = context.cache_key(query)
        scope_key = key[:4]

        def _do() -> None:
            try:
                hits = context.client.search(
                    query=query, limit=_PREFETCH_RESULTS, **context.search_params()
                )
            except Exception:
                log.warning("ai-memory queue_prefetch failed", exc_info=True)
                return
            with self._lock:
                if context.generation != self._generation:
                    return
                self._prefetch_cache[key] = hits
                self._prefetch_latest[scope_key] = (query, hits)
                while len(self._prefetch_cache) > _PREFETCH_CACHE_MAX:
                    self._prefetch_cache.pop(next(iter(self._prefetch_cache)))
                while len(self._prefetch_latest) > _PREFETCH_CACHE_MAX:
                    self._prefetch_latest.pop(next(iter(self._prefetch_latest)))

        self._spawn_worker(_do, name="ai-memory-prefetch")

    def recall_status(self) -> RecallStatus | None:
        """Hit count from the most recent ``prefetch``, for Hermes's indicator."""
        if self._last_recall_count <= 0:
            return None
        return RecallStatus(provider_label=self.name, count=self._last_recall_count)

    def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
        context = self._snapshot(session_id)
        if not self._has_write_scope(context):
            return
        sid, ws, proj, cwd = (
            context.session_id, context.workspace, context.project, context.cwd
        )

        def _do() -> None:
            try:
                # ai-memory's own lifecycle event. The previous
                # event="user-prompt" with a {user, assistant} body was
                # accepted with 202 and then stored with an EMPTY body,
                # because ai-memory reads `prompt` off a
                # `user-prompt-submit` payload. Every Hermes turn was lost.
                context.client.send_hook(
                    event="user-prompt-submit",
                    session_id=sid,
                    payload={"session_id": sid, "prompt": user},
                    workspace=ws,
                    project=proj,
                    cwd=cwd,
                )
            except Exception:
                log.warning("ai-memory sync_turn failed", exc_info=True)

        self._spawn_worker(_do, name="ai-memory-sync-turn")

    def on_session_end(self, messages: list[dict[str, Any]], **kwargs: Any) -> None:
        context = self._snapshot()
        if not self._has_write_scope(context):
            return
        sid, ws, proj, cwd = (
            context.session_id, context.workspace, context.project, context.cwd
        )

        def _do() -> None:
            try:
                # ai-memory reads no body field on SessionEnd: the event closes
                # the session, synthesizes sessions/<id>.md and writes the auto
                # handoff. Posting the transcript only risked the 0.5s turn-hook
                # timeout dropping the close, so the payload stays minimal and
                # the call gets the write budget instead.
                context.client.send_hook(
                    event="session-end",
                    session_id=sid,
                    payload={"session_id": sid},
                    workspace=ws,
                    project=proj,
                    cwd=cwd,
                    timeout=SESSION_END_TIMEOUT,
                )
            except Exception:
                log.warning("ai-memory on_session_end failed", exc_info=True)

        self._spawn_worker(
            _do, name="ai-memory-session-end", join_budget=_SESSION_END_JOIN_TIMEOUT
        )

    # Hermes announces built-in memory writes as add|replace|remove; write and
    # append are kept as synonyms for older callers of this hook.
    _MIRRORED_ACTIONS = ("add", "replace", "write", "append")
    _REPLACED_HEADING = "## Substituído"

    def on_memory_write(
        self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Mirror a built-in `MEMORY.md` / `USER.md` write into the wiki.

        ``remove`` is the native store deleting an entry it owns: the mirror
        keeps the page history instead of writing a tombstone, so it is
        skipped. A ``replace`` carries the superseded entry in
        ``metadata["previous_content"]``, which is kept in the mirrored page so
        the replacement does not silently drop it.
        """
        context = self._snapshot()
        if not self._has_write_scope(context):
            return
        if action not in self._MIRRORED_ACTIONS:
            return

        meta = metadata or {}
        previous = str(meta.get("previous_content") or meta.get("old_text") or "")
        body = content
        if action == "replace" and previous:
            body = f"{content}\n\n{self._REPLACED_HEADING}\n\n{previous}"

        path = f"hermes-memory/{target}.md"

        def _do() -> None:
            try:
                context.client.write_page(
                    path=path,
                    body=body,
                    tags=["hermes", "mirror"],
                    workspace=context.workspace,
                    project=context.project,
                )
            except Exception:
                log.warning("on_memory_write hook failed", exc_info=True)

        # Hermes calls this INLINE in the tool loop (agent/memory_manager.py:
        # 744-761); a 10s write timeout there would stall the user's turn.
        # Mirror on a tracked background thread, like the bundled byterover
        # provider does for memory writes.
        self._spawn_worker(_do, name="ai-memory-memory-write")

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs: Any,
    ) -> None:
        """Follow /new, /reset, /resume, /branch and context compression.

        Signature mirrors ``MemoryProvider.on_session_switch``. Hermes swaps
        session_id on these paths without rebuilding the provider, so without
        this every later observation kept the id of the session the provider
        was first initialized with.
        """
        with self._lock:
            self.session_id = new_session_id
            self._generation += 1
            self._prefetch_cache.clear()
            self._prefetch_latest.clear()
            self._last_recall_count = 0
            if reset:
                # A reset starts a clean context; the previous session's
                # handoff must not leak into it.
                self._handoff_context = None

    def _spawn_worker(
        self,
        target: Callable[[], None],
        *,
        name: str,
        join_budget: float = _SHUTDOWN_JOIN_TIMEOUT,
    ) -> None:
        """Start provider background work through the host's context-aware spawner.

        Hermes requires ``agent.memory_provider.spawn_context_thread`` so the
        worker inherits the caller's contextvars (profile isolation and the
        per-turn secret scope); a bare thread starts with an empty context and
        under multiplexed profiles writes to the default profile
        (agent/memory_provider.py:29-33,
        website/docs/developer-guide/memory-provider-plugin.md:394-412).
        Fall back to a daemon thread when Hermes is not importable so the
        plugin still works standalone.

        The whole check-start-track sequence runs under ``self._lock``, so a
        thread in ``_worker_threads`` is always running or finished: shutdown()
        can never observe a tracked-but-unstarted thread and skip it. A spawn
        that arrives once shutdown has begun runs inline instead of creating an
        untracked daemon that would outlive the join.
        """
        spawn_context_thread: Callable[..., threading.Thread] | None = None
        try:
            from agent.memory_provider import (  # type: ignore[import-untyped]
                spawn_context_thread as _spawn_context_thread,
            )
        except Exception:
            pass
        else:
            spawn_context_thread = _spawn_context_thread
        with self._lock:
            if self._shutting_down:
                run_inline = True
            else:
                if spawn_context_thread is not None:
                    try:
                        thread = spawn_context_thread(target, name=name)
                    except Exception:
                        log.debug(
                            "ai-memory: spawn_context_thread failed; using a daemon thread",
                            exc_info=True,
                        )
                        thread = threading.Thread(target=target, name=name, daemon=True)
                else:
                    thread = threading.Thread(target=target, name=name, daemon=True)
                self._prune_workers_locked()
                thread.start()
                # Append after start() and still under the lock: shutdown()'s
                # snapshot therefore only sees running (or already finished)
                # workers.
                self._worker_threads.append(_TrackedWorker(thread, join_budget))
                run_inline = False
        if run_inline:
            log.debug("ai-memory: shutdown in progress; running %s inline", name)
            target()

    def _prune_workers_locked(self) -> None:
        """Drop finished threads before appending a new one (call under the lock)."""
        alive: list[_TrackedWorker] = []
        for worker in self._worker_threads:
            try:
                is_alive = getattr(worker.thread, "is_alive", None)
                if is_alive is None or is_alive():
                    alive.append(worker)
            except Exception:
                alive.append(worker)
        self._worker_threads = alive

    def shutdown(self) -> None:
        """Join our background workers, bounded, before Hermes exits.

        Hermes calls ``on_session_end`` and then ``shutdown_all()``; its drain
        is bounded at 5s (``_SYNC_DRAIN_TIMEOUT_S``,
        agent/memory_manager.py:41) and only covers the manager's own executor
        (``_drain_sync_executor``, agent/memory_manager.py:870-905). It cannot
        see our threads, so join them here.

        Workers are joined longest-budget-first so the session-end POST (which
        carries the client's 10s ``SESSION_END_TIMEOUT``) gets its own budget
        instead of sharing a 5s slice with shorter workers. The overall wait is
        capped at ``_MAX_SHUTDOWN_JOIN_TIMEOUT`` so shutdown stays bounded.
        Finished workers are joined anyway: ``join()`` on a finished thread is
        immediate, and an unstarted thread in the tracking list must not be
        silently skipped.
        """
        with self._lock:
            self._shutting_down = True
            workers = self._worker_threads
            self._worker_threads = []
        workers.sort(key=lambda worker: worker.join_budget, reverse=True)
        deadline = time.monotonic() + _MAX_SHUTDOWN_JOIN_TIMEOUT
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.debug("ai-memory shutdown join budget exhausted")
                break
            try:
                worker.thread.join(timeout=min(worker.join_budget, remaining))
            except Exception:
                log.debug("ai-memory worker join failed", exc_info=True)

    def _search(
        self, args: dict[str, Any], *, context: _OperationContext | None = None
    ) -> dict[str, Any]:
        query = args.get("query", "")
        max_results = args.get("max_results", 5)
        if not isinstance(max_results, int) or isinstance(max_results, bool):
            max_results = 5
        context = context or self._snapshot()
        if context.search_scope == "project" and not context.scope_known:
            return {"ok": False, "error": "Project scope is unknown", "results": []}
        results = context.client.search(
            query=query, limit=max_results, **context.search_params()
        )
        return {"ok": True, "results": results}

    def _write(self, args: dict[str, Any]) -> dict[str, Any]:
        context = self._snapshot()
        if not self._has_write_scope(context):
            return {"ok": False, "error": "Write disabled: project scope is unknown or non-primary"}
        result = context.client.write_page(
            path=args.get("path", ""),
            body=args.get("body", ""),
            tags=args.get("tags"),
            workspace=context.workspace,
            project=context.project,
        )
        if not (result.get("ok", False) or result.get("page_id")):
            return result
        return {"ok": True, "written": args.get("path")}

    def _status(self) -> dict[str, Any]:
        return self._client.status()
