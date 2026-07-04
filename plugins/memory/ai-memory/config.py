from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SERVER_URL = "http://127.0.0.1:49374"


@dataclass
class AiMemoryConfig:
    server_url: str = DEFAULT_SERVER_URL
    api_key: str = ""
    auth_token: str = ""
    workspace: str = "hermes"
    project: str = "hermes-default"


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
            "required": False,
            "env_var": "AI_MEMORY_API_KEY",
        },
        {
            "key": "auth_token",
            "description": "ai-memory auth token (optional for local mode)",
            "secret": True,
            "required": False,
            "env_var": "AI_MEMORY_AUTH_TOKEN",
        },
        {
            "key": "workspace",
            "description": "ai-memory workspace name",
            "default": "hermes",
            "required": False,
        },
        {
            "key": "project",
            "description": "ai-memory project name",
            "default": "hermes-default",
            "required": False,
        },
    ]


def save_config(values: dict[str, Any], hermes_home: str) -> None:
    p = Path(hermes_home) / "ai-memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            pass
    existing.update(values)
    p.write_text(json.dumps(existing, indent=2))


def load_config(hermes_home: str) -> AiMemoryConfig:
    p = Path(hermes_home) / "ai-memory.json"
    overrides: dict[str, Any] = {}

    if p.exists():
        try:
            overrides = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    env_map: dict[str, str] = {
        "AI_MEMORY_SERVER_URL": "server_url",
        "AI_MEMORY_AUTH_TOKEN": "auth_token",
        "AI_MEMORY_API_KEY": "api_key",
    }
    for env_key, attr in env_map.items():
        val = os.environ.get(env_key)
        if val:
            overrides[attr] = val

    overrides.setdefault("server_url", DEFAULT_SERVER_URL)

    return AiMemoryConfig(**{k: v for k, v in overrides.items() if hasattr(AiMemoryConfig, k)})
