from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import httpx

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from config import AiMemoryConfig  # noqa: E402

log = logging.getLogger("ai-memory")

SEARCH_TIMEOUT = 10.0
HOOK_TIMEOUT = 0.5
WRITE_TIMEOUT = 10.0


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

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base}{path}"
        extra_headers = kwargs.pop("headers", {})
        headers = {**self._client.headers, **extra_headers}
        timeout = kwargs.pop("timeout", SEARCH_TIMEOUT)
        if self._transport:
            with httpx.Client(transport=self._transport, timeout=timeout) as c:
                return c.request(method, url, headers=headers, **kwargs)
        return self._client.request(method, url, headers=headers, timeout=timeout, **kwargs)

    def search(
        self,
        query: str,
        workspace: str | None = None,
        project: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if workspace:
            params["workspace"] = workspace
        if project:
            params["project"] = project
        r = self._request("GET", "/admin/search", params=params, timeout=SEARCH_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            log.warning("search response is not a dict: %s", type(data).__name__)
            return []
        return data.get("results", data.get("pages", []))

    def write_page(
        self,
        path: str,
        body: str,
        tags: list[str] | None = None,
        tier: str | None = None,
        pinned: bool = False,
        workspace: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path, "body": body}
        if tags:
            payload["tags"] = tags
        if tier:
            payload["tier"] = tier
        if pinned:
            payload["pinned"] = pinned
        if workspace:
            payload["workspace"] = workspace
        if project:
            payload["project"] = project
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
    ) -> None:
        params: dict[str, str] = {
            "event": event,
            "agent": "hermes",
        }
        if workspace:
            params["workspace"] = workspace
        if project:
            params["project"] = project
        if session_id:
            params["session_id"] = session_id
        body: dict[str, Any] = {}
        if payload:
            body = payload
        try:
            self._request("POST", "/hook", params=params, json=body, timeout=HOOK_TIMEOUT)
        except Exception:
            log.exception("hook failed for event=%s", event)

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
        if workspace:
            params["workspace"] = workspace
        if project:
            params["project"] = project
        r = self._request("GET", "/handoff", params=params, timeout=SEARCH_TIMEOUT)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return data.get("handoff", {}).get("summary")
