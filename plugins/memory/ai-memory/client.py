from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from config import AiMemoryConfig, marker_briefing  # noqa: E402

log = logging.getLogger("ai-memory")

# Hermes abandons an external provider prefetch after 8s
# (agent/memory_manager.py:42 and :388-395), keeping the call running in the
# background but discarding its result. A search that outlives that window is
# therefore wasted, so stay comfortably under the host bound. Session end does
# not share this budget; it keeps the longer SESSION_END_TIMEOUT below.
SEARCH_TIMEOUT = 5.0
HOOK_TIMEOUT = 0.5
WRITE_TIMEOUT = 10.0
# Handoff is fetched once, synchronously, on session start against a
# loopback server. Keep it short so a stalled server cannot delay startup.
HANDOFF_TIMEOUT = 2.0
# Session end carries no transcript (ai-memory stores only the lifecycle row),
# so it gets the write budget instead of the 0.5s turn-hook budget.
SESSION_END_TIMEOUT = 10.0
# A local server that is down fails every call immediately; after this many
# consecutive transport failures the client pauses instead of paying a timeout
# on every turn. ``last_failure()`` explains the pause.
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60.0


class AiMemoryClient:
    def __init__(self, config: AiMemoryConfig) -> None:
        self.config = config
        self._base = config.server_url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = config.auth_token or config.api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._transport: Any = None
        self._client = httpx.Client(headers=headers)
        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._last_failure = ""

    def last_failure(self) -> str:
        """Transport failure pausing this client, or ``""`` while it is healthy."""
        return self._last_failure if self._is_blocked() else ""

    def _is_blocked(self) -> bool:
        """Whether the pause window is still open; expires into a fresh attempt."""
        if not self._blocked_until:
            return False
        if time.monotonic() >= self._blocked_until:
            self._blocked_until = 0.0
            self._consecutive_failures = 0
            self._last_failure = ""
            return False
        return True

    def _record_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        self._last_failure = f"{type(exc).__name__}: {exc}"
        if self._consecutive_failures >= FAILURE_THRESHOLD:
            self._blocked_until = time.monotonic() + COOLDOWN_SECONDS
            log.warning(
                "ai-memory unreachable (%d consecutive failures, %s); pausing requests for %.0fs",
                self._consecutive_failures,
                self._last_failure,
                COOLDOWN_SECONDS,
            )

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._last_failure = ""

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._is_blocked():
            raise RuntimeError(f"ai-memory requests paused: {self._last_failure}")
        url = f"{self._base}{path}"
        extra_headers = kwargs.pop("headers", {})
        headers = {**self._client.headers, **extra_headers}
        timeout = kwargs.pop("timeout", SEARCH_TIMEOUT)
        try:
            if self._transport:
                with httpx.Client(transport=self._transport, timeout=timeout) as c:
                    response = c.request(method, url, headers=headers, **kwargs)
            else:
                response = self._client.request(
                    method, url, headers=headers, timeout=timeout, **kwargs
                )
        except Exception as exc:
            self._record_failure(exc)
            raise
        self._record_success()
        return response

    def search(
        self,
        query: str,
        workspace: str | None = None,
        project: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Full-text search the ai-memory wiki.

        ``GET /admin/search?q=&limit=`` is the right route because it is
        always mounted: the admin router is merged into every serving
        surface (``serve.rs:1908``). The ``POST /api/v1/search`` route this
        used to call does exist (``crates/ai-memory-web/src/routes/api.rs:
        41-43``), but the ``/api/v1`` router is only mounted when the server
        is started with ``--enable-api`` or ``--enable-web``
        (``serve.rs:1873``), both off by default — so it 404s on a default
        install, which is why we do not use it.

        Contract re-verified against ai-memory 3.2.0 (3.x); the route and
        response shape below are unchanged from 1.28.1.

        Scope is all-or-nothing. ai-memory resolves a project *within* a
        workspace, so a lone ``project=`` has no workspace to resolve
        against, and passing only one of the pair is rejected outright:
        ``GET /admin/search`` answers HTTP 400 ``"workspace and project must
        be provided together"``
        (``crates/ai-memory-mcp/src/admin.rs:1775-1778``). Passing neither
        searches globally, across every project — which is what cross-agent
        recall needs.
        """
        params: dict[str, Any] = {"q": query, "limit": limit}
        if workspace and project:
            params["workspace"] = workspace
            params["project"] = project
        r = self._request("GET", "/admin/search", params=params, timeout=SEARCH_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            data = data.get("results", data.get("pages", []))
        if not isinstance(data, list):
            log.warning("search response has unexpected type: %s", type(data).__name__)
            return []
        return [item for item in data if isinstance(item, dict)][:limit]

    def write_page(
        self,
        path: str,
        body: str,
        tags: list[str] | None = None,
        tier: str | None = None,
        pinned: bool = False,
        workspace: str = "",
        project: str = "",
    ) -> dict[str, Any]:
        # ai-memory's ``WritePageAdminRequest`` declares ``workspace`` and
        # ``project`` as required strings, not options
        # (``crates/ai-memory-mcp/src/admin.rs:8342-8347``), so a missing
        # field is an Axum JSON rejection (422). Always send both and fail
        # here, where the message names the problem, rather than leaving the
        # caller to decode a remote 422.
        workspace = workspace or ""
        project = project or ""
        if not workspace.strip() or not project.strip():
            raise ValueError("write_page requires both workspace and project")
        payload: dict[str, Any] = {
            "path": path,
            "body": body,
            "workspace": workspace,
            "project": project,
        }
        if tags:
            payload["tags"] = tags
        if tier:
            payload["tier"] = tier
        if pinned:
            payload["pinned"] = pinned
        r = self._request("POST", "/admin/write-page", json=payload, timeout=WRITE_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def status(self) -> dict[str, Any]:
        r = self._request("GET", "/admin/status", timeout=SEARCH_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def send_hook(
        self,
        event: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
        workspace: str | None = None,
        project: str | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> None:
        if self._is_blocked():
            log.debug("ai-memory hook skipped for event=%s: %s", event, self._last_failure)
            return
        params: dict[str, str] = {
            "event": event,
            "agent": "hermes",
        }
        if workspace:
            params["workspace"] = workspace
        if project:
            params["project"] = project
        # cwd travels with the event so the server can resolve the same scope a
        # shell-hook-driven agent would, and refresh the active project.
        if cwd:
            params["cwd"] = cwd
        if session_id:
            params["session_id"] = session_id
        body: dict[str, Any] = {}
        if payload:
            body = payload
        try:
            r = self._request(
                "POST", "/hook", params=params, json=body, timeout=timeout or HOOK_TIMEOUT
            )
            # ai-memory answers 202 for anything it queues, including a
            # payload whose fields it does not recognise, so a bad shape
            # used to look identical to a good one. raise_for_status at
            # least surfaces transport- and route-level failures.
            r.raise_for_status()
        except Exception:
            log.warning("ai-memory hook failed for event=%s", event, exc_info=True)

    def fetch_handoff(
        self,
        agent: str = "hermes",
        cwd: str | None = None,
        workspace: str | None = None,
        project: str | None = None,
    ) -> str | None:
        params: dict[str, str] = {"agent": agent}
        if cwd:
            params["cwd"] = cwd
            briefing = marker_briefing(cwd)
            if briefing.get("inject_on_session_start", "").lower() in ("1", "true", "yes", "on"):
                # ai-memory only appends the project brief (pinned/_rules_/
                # _slots_ pages) when the client forwards the marker's opt-in;
                # the hook clients do, this provider predates it.
                params["briefing"] = briefing["inject_on_session_start"]
                if briefing.get("max_chars"):
                    params["briefing_budget"] = briefing["max_chars"]
        if workspace:
            params["workspace"] = workspace
        if project:
            params["project"] = project
        r = self._request("GET", "/handoff", params=params, timeout=HANDOFF_TIMEOUT)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        # ai-memory 3.x (verified against 3.2.0) returns the handoff as a
        # markdown block, not a JSON envelope: r.json() raised here on every
        # call.
        text = (r.text or "").strip()
        return text or None
