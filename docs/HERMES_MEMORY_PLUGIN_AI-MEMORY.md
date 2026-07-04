
# Hermes Memory Provider Plugin for ai-memory

> Research + implementation guide for connecting [ai-memory](https://github.com/akitaonrails/ai-memory) to Hermes Agent as a first-class memory provider plugin.

**Status**: Research complete. `ai-memory` is not a built-in Hermes provider, but it can be integrated via the `MemoryProvider` plugin interface or via MCP. This document covers the native plugin route.

---

## 1. Background

### What is ai-memory?

`ai-memory` (by akitaonrails) is a long-term memory system for AI coding agents. It stores observations in a plain-markdown wiki inside a git repo, backed by SQLite with FTS5 and optional embeddings. Key properties:

- Zero-friction capture via lifecycle hooks
- Cross-agent handoffs (Claude Code, Codex, OpenCode, etc.)
- Per-project isolation keyed by workspace UUID
- LLM-assisted consolidation is opt-in
- Exposes an MCP server and a local HTTP API

Relevant repo: https://github.com/akitaonrails/ai-memory

### What are Hermes memory providers?

Hermes Agent ships with a plugin interface for external memory backends. Native providers (Holographic, Mem0, Hindsight, RetainDB, Supermemory, Memori, ByteRover, Honcho, OpenViking) get:

- Automatic `prefetch()` before every model turn
- Automatic `sync_turn()` after each completed turn
- `on_session_end()` for final extraction
- `on_pre_compress()` to preserve insights before context compaction
- `system_prompt_block()` injection
- Profile isolation via `$HERMES_HOME`

Only one provider is active at a time. Built-in `MEMORY.md` / `USER.md` always remain additive.

Docs: https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin

---

## 2. Integration Options

| Approach | Effort | Auto-injection | Isolation | Recommendation |
|---|---|---|---|---|
| **MCP server** | Low | Manual tool calls only | Shared repo | Fastest path, no plugin code |
| **Memory provider plugin** | Medium | Full Hermes hook integration | Per-profile config | Best long-term UX |
| **Subprocess CLI wrapper** | Medium | Depends on plugin | Moderate | Good if ai-memory has no HTTP API |

The rest of this document covers **Option B: native memory provider plugin**, because it gives the deepest Hermes integration.

---

## 3. Plugin Structure

```
plugins/memory/ai-memory/
├── __init__.py       # MemoryProvider implementation + register()
├── plugin.yaml       # Metadata
└── README.md         # Setup instructions
```

---

## 4. Core Implementation

### 4.1 `__init__.py` skeleton

```python
import os
import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from agent.memory_provider import MemoryProvider


class AiMemoryProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "ai-memory"

    # ------------------------------------------------------------------
    # Availability / init
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Quick check: env vars or default local server."""
        return bool(
            os.environ.get("AI_MEMORY_API_KEY")
            or os.environ.get("AI_MEMORY_SERVER_URL")
            or Path(os.environ.get("AI_MEMORY_DATA_DIR", "")).exists()
        )

    def initialize(self, session_id: str, **kwargs) -> None:
        self.server = os.environ.get(
            "AI_MEMORY_SERVER_URL",
            kwargs.get("ai_memory_server_url", "http://127.0.0.1:3113"),
        ).rstrip("/")
        self.api_key = os.environ.get("AI_MEMORY_API_KEY", "")
        self.data_dir = os.environ.get(
            "AI_MEMORY_DATA_DIR",
            kwargs.get("ai_memory_data_dir", ""),
        )
        self.session_id = session_id
        self._lock = threading.Lock()
        self._config_path = Path(kwargs.get("hermes_home", "~/.hermes")) / "ai-memory.json"
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Config (used by `hermes memory setup` wizard)
    # ------------------------------------------------------------------
    def get_config_schema(self):
        return [
            {
                "key": "api_key",
                "description": "ai-memory API key (optional for local mode)",
                "secret": True,
                "required": False,
                "env_var": "AI_MEMORY_API_KEY",
            },
            {
                "key": "server_url",
                "description": "ai-memory server URL",
                "default": "http://127.0.0.1:3113",
                "required": False,
            },
            {
                "key": "data_dir",
                "description": "ai-memory data directory (wiki + db)",
                "required": False,
            },
        ]

    def save_config(self, values: dict, hermes_home: str) -> None:
        p = Path(hermes_home) / "ai-memory.json"
        existing = {}
        if p.exists():
            try:
                existing = json.loads(p.read_text())
            except Exception:
                pass
        existing.update(values)
        p.write_text(json.dumps(existing, indent=2))

    def _load_saved_config(self) -> dict:
        if self._config_path.exists():
            try:
                return json.loads(self._config_path.read_text())
            except Exception:
                return {}
        return {}

    # ------------------------------------------------------------------
    # Tool exposure (agent can call these explicitly)
    # ------------------------------------------------------------------
    def get_tool_schemas(self):
        return [
            {
                "name": "ai_memory_search",
                "description": "Search the ai-memory wiki for relevant context",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "ai_memory_write",
                "description": "Write a new page or memory to the ai-memory wiki",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "content"],
                },
            },
            {
                "name": "ai_memory_status",
                "description": "Check ai-memory server / wiki health",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs):
        if tool_name == "ai_memory_search":
            return self._search(args)
        if tool_name == "ai_memory_write":
            return self._write(args)
        if tool_name == "ai_memory_status":
            return self._status()
        raise ValueError(f"Unknown tool: {tool_name}")

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    def system_prompt_block(self) -> str:
        """Inject static provider info into system prompt (optional)."""
        return "Long-term memory is backed by ai-memory wiki."

    def prefetch(self, query: str, *, session_id: str = "") -> str | None:
        """Called before each model turn. Return recalled context or None."""
        result = self._search({"query": query, "max_results": 3})
        if result.get("ok") and result.get("results"):
            return "\n\n".join(r.get("snippet", "") for r in result["results"])
        return None

    def queue_prefetch(self, query: str) -> None:
        """Pre-warm context for next turn (non-blocking)."""
        threading.Thread(target=self.prefetch, args=(query,), daemon=True).start()

    def sync_turn(self, user: str, assistant: str, *, session_id: str = "") -> None:
        """Capture each completed turn into ai-memory."""
        # Optional: send to ai-memory inbox for later consolidation
        payload = json.dumps({
            "session_id": session_id or self.session_id,
            "user": user,
            "assistant": assistant,
        }).encode()
        self._post("/api/v1/observe", payload)

    def on_session_end(self, messages) -> None:
        """Final flush when conversation ends."""
        # Optional: trigger consolidation in ai-memory
        self._post("/api/v1/session/end", json.dumps({
            "session_id": self.session_id,
        }).encode())

    def on_pre_compress(self, messages) -> None:
        """Save insights before Hermes discards context."""
        # Optional: nothing, or push a summary to ai-memory
        pass

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Mirror built-in MEMORY.md writes to ai-memory wiki."""
        if action in ("write", "append"):
            self._write({
                "title": f"Hermes Memory :: {target}",
                "content": content,
                "tags": ["hermes", "mirror"],
            })

    def shutdown(self) -> None:
        """Cleanup on process exit."""
        pass

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.server}{path}"

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str):
        req = Request(self._url(path), headers=self._headers(), method="GET")
        try:
            with urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except HTTPError as e:
            return {"ok": False, "error": str(e), "status": e.code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _post(self, path: str, data: bytes):
        req = Request(
            self._url(path),
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------
    def _search(self, args: dict):
        q = args.get("query", "")
        max_results = args.get("max_results", 5)
        # Adjust endpoint to match ai-memory's actual HTTP API
        data = self._get(f"/api/v1/wiki/search?q={q}&limit={max_results}")
        if data.get("ok"):
            return {"ok": True, "results": data.get("results", [])}
        return data

    def _write(self, args: dict):
        payload = json.dumps({
            "title": args.get("title", ""),
            "content": args.get("content", ""),
            "tags": args.get("tags", []),
            "session_id": self.session_id,
        }).encode()
        result = self._post("/api/v1/wiki/write", payload)
        return result or {"ok": True, "written": args.get("title")}

    def _status(self):
        data = self._get("/api/v1/health")
        return data if data else {"ok": True, "service": "ai-memory", "url": self.server}


def register():
    """Entry point called by Hermes plugin loader."""
    return AiMemoryProvider
```

---

## 5. Plugin Metadata

### `plugin.yaml`

```yaml
name: ai-memory
description: ai-memory wiki-backed long-term memory provider
provider_type: memory
entry_point: __init__.py
```

### `README.md` (minimal)

```markdown
# ai-memory Hermes Memory Provider

Connects Hermes Agent to an ai-memory server for long-term wiki memory.

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server running locally or on LAN

## Setup

1. Start ai-memory:
   curl -fsSL https://raw.githubusercontent.com/alphaonedev/ai-memory-mcp/main/install.sh | sh
   ai-memory serve --db ~/.ai-memory/wiki.db

2. Install the plugin:
   mkdir -p ~/.hermes/plugins/memory/ai-memory
   cp __init__.py plugin.yaml README.md ~/.hermes/plugins/memory/ai-memory/

3. Enable in Hermes:
   hermes plugins enable ai-memory
   hermes memory setup   # enter server URL and optional API key

4. Verify:
   hermes memory status

## Tools exposed

- `ai_memory_search` — search the wiki
- `ai_memory_write` — write a new page
- `ai_memory_status` — health check
```

---

## 6. Configuration Details

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `AI_MEMORY_SERVER_URL` | ai-memory HTTP/MCP server | `http://127.0.0.1:3113` |
| `AI_MEMORY_API_KEY` | Bearer token if auth enabled | empty |
| `AI_MEMORY_DATA_DIR` | Path to ai-memory wiki directory | empty |

### Hermes config (`~/.hermes/config.yaml` alt-form)

```yaml
memory:
  provider: ai-memory
  ai_memory_server_url: "http://127.0.0.1:3113"
  # ai_memory_api_key is stored in $HERMES_HOME/.env or .env file
```

### Profile isolation

Each Hermes profile gets its own ai-memory project namespace by default if you include the profile name in the data dir or pass it as a prefix when writing. Add this in `initialize()`:

```python
profile = os.environ.get("HERMES_PROFILE", "default")
self.project_id = f"hermes-{profile}"
```

Then tag every write with `project_id`.

---

## 7. HTTP API Contract (adjust to real ai-memory)

The `_get` / `_post` helpers above assume these endpoints on the ai-memory server. **Verify against the actual binary / server you run**:

| Hermes action | ai-memory endpoint | Method |
|---|---|---|
| Search | `/api/v1/wiki/search?q=<query>&limit=<n>` | GET |
| Write page | `/api/v1/wiki/write` | POST |
| Health | `/api/v1/health` | GET |
| Observe turn | `/api/v1/observe` | POST |
| Session end | `/api/v1/session/end` | POST |

If ai-memory exposes different paths (e.g. `/mcp`, `/wiki/search`), update the `_url()` call sites.

### MCP alternative (no custom plugin)

If you prefer zero plugin code, add ai-memory's bundled MCP server to Hermes:

```yaml
mcp:
  servers:
    ai-memory:
      command: ai-memory
      args: ["mcp", "--tier", "semantic"]
```

Then use tools from chat. You lose auto-injection but gain immediate functionality.

---

## 8. Implementation Priorities

1. **`is_available()` + `initialize()` + `get_config_schema()`** — enable `hermes memory setup`
2. **`get_tool_schemas()` + `handle_tool_call()`** — expose `ai_memory_search` / `ai_memory_write`
3. **`prefetch()`** — inject recalled context before model turns (highest value)
4. **`sync_turn()`** — capture ongoing conversation
5. **`on_session_end()`** — finalize and consolidate
6. **`on_memory_write()`** — mirror MEMORY.md writes

You can ship steps 1-2 immediately and add hooks incrementally.

---

## 9. Testing Checklist

- [ ] `hermes plugins list` shows `ai-memory`
- [ ] `hermes memory setup` accepts server URL / API key
- [ ] `hermes memory status` reports `ok: true`
- [ ] `ai_memory_search` returns results from wiki
- [ ] `ai_memory_write` creates a new page
- [ ] Conversation turns are captured (`sync_turn` called)
- [ ] Context is injected before model turn (`prefetch` called)
- [ ] Session end flushes without error
- [ ] Switching profiles isolates writes to per-profile namespace

---

## 10. References

- Hermes Memory Provider Plugin docs: https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin
- Community precedent (agentmemory plugin): https://github.com/NousResearch/hermes-agent/issues/6715
- ai-memory repo: https://github.com/akitaonrails/ai-memory
- ai-memory MCP server (alphaonedev fork): https://github.com/alphaonedev/ai-memory-mcp
- ai-memory MCP listing: https://mcpservers.org/servers/alphaonedev/ai-memory-mcp

---

## 11. Open Questions To Resolve

1. **Exact ai-memory HTTP API paths** — confirm against the running binary (`ai-memory serve --help` or source).
2. **Auth model** — bearer token? mTLS? None by default on loopback?
3. **Write conflict handling** — ai-memory is git-backed; concurrent Hermes writes from multiple profiles may need serialization.
4. **Plugin API stability** — confirm `agent.memory_provider.MemoryProvider` import path in your installed Hermes version.
5. **TOON vs JSON** — if ai-memory supports TOON responses, use them to cut context cost.

