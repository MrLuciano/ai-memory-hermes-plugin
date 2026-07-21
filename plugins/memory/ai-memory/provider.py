from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from client import AiMemoryClient  # noqa: E402
from config import AiMemoryConfig, get_config_schema, load_config, save_config  # noqa: E402

try:
    from agent.memory_provider import MemoryProvider  # type: ignore[import-untyped]
except ImportError:
    from abc import ABC as _ABC

    class MemoryProvider(_ABC):  # type: ignore[no-redef]
        pass

log = logging.getLogger(__name__)


class AiMemoryProvider(MemoryProvider):
    def __init__(
        self,
        client: AiMemoryClient | None = None,
        config: AiMemoryConfig | None = None,
    ) -> None:
        self._config = config or AiMemoryConfig()
        self._client = client or AiMemoryClient(self._config)
        self._lock = threading.Lock()
        self.session_id: str = ""
        self._hermes_home: str = ""

    @property
    def name(self) -> str:
        return "ai-memory"

    def is_available(self) -> bool:
        # ai-memory does not require authentication by default; the provider
        # is available whenever a server URL is configured.
        return bool(self._config.server_url)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self.session_id = session_id
        hermes_home = kwargs.get("hermes_home", "")
        self._hermes_home = hermes_home

        with self._lock:
            if hermes_home:
                self._config = load_config(hermes_home)
                self._client = AiMemoryClient(self._config)

            server_url = kwargs.get("ai_memory_server_url", "")
            if server_url:
                self._config.server_url = server_url

            auth_token = kwargs.get("ai_memory_auth_token", "")
            if auth_token:
                self._config.auth_token = auth_token

            workspace = kwargs.get("ai_memory_workspace", "")
            if workspace:
                self._config.workspace = workspace

            project = kwargs.get("project", "")
            if project:
                self._config.project = project
            else:
                profile = kwargs.get("profile", "default")
                self._config.project = f"hermes-{profile}"

            self._client = AiMemoryClient(self._config)

    def get_config_schema(self) -> list[dict[str, Any]]:
        return get_config_schema()

    def save_config(self, values: dict[str, Any], hermes_home: str) -> list[str]:
        return save_config(values, hermes_home)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "ai_memory_search",
                "description": "Search the ai-memory wiki for relevant context",
                "input_schema": {
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
                "input_schema": {
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
                "input_schema": {"type": "object", "properties": {}},
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

    def system_prompt_block(self) -> str:
        return "Long-term memory is backed by ai-memory wiki."

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        results = self._search({"query": query, "max_results": 3})
        if results.get("ok") and results.get("results"):
            return "\n\n".join(r.get("snippet", "") for r in results["results"])
        return ""

    def queue_prefetch(self, query: str) -> None:
        threading.Thread(target=self.prefetch, args=(query,), daemon=True).start()

    def sync_turn(self, user: str, assistant: str, *, session_id: str = "", **kwargs: Any) -> None:
        sid = session_id or self.session_id
        ws = self._config.workspace
        proj = self._config.project

        def _do() -> None:
            try:
                self._client.send_hook(
                    event="user-prompt",
                    session_id=sid,
                    payload={"user": user, "assistant": assistant},
                    workspace=ws,
                    project=proj,
                )
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    def on_session_end(self, messages: list[dict[str, Any]], **kwargs: Any) -> None:
        sid = self.session_id
        ws = self._config.workspace
        proj = self._config.project

        def _do() -> None:
            try:
                self._client.send_hook(
                    event="session-end",
                    session_id=sid,
                    payload={"messages": messages},
                    workspace=ws,
                    project=proj,
                )
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    def on_memory_write(
        self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        if action in ("write", "append"):
            try:
                self._client.write_page(
                    path=f"hermes-memory/{target}.md",
                    body=content,
                    tags=["hermes", "mirror"],
                    workspace=self._config.workspace,
                    project=self._config.project,
                )
            except Exception:
                log.warning("on_memory_write hook failed", exc_info=True)

    def shutdown(self) -> None:
        pass

    def _search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        max_results = args.get("max_results", 5)
        results = self._client.search(
            query=query,
            limit=max_results,
            workspace=self._config.workspace,
            project=self._config.project,
        )
        return {"ok": True, "results": results}

    def _write(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self._client.write_page(
            path=args.get("path", ""),
            body=args.get("body", ""),
            tags=args.get("tags"),
            workspace=self._config.workspace,
            project=self._config.project,
        )
        if not result.get("ok", False):
            return result
        return {"ok": True, "written": args.get("path")}

    def _status(self) -> dict[str, Any]:
        return self._client.status()
