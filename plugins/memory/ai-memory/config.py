from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

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
            existing = json.loads(p.read_text())
        except Exception:
            pass

    # Also strip any secrets already persisted in the file
    for secret_key in secrets:
        existing.pop(secret_key, None)

    existing.update(safe_values)
    p.write_text(json.dumps(existing, indent=2))
    return skipped


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
