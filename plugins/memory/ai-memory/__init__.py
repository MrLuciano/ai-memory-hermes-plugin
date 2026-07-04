from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_init_dir = str(Path(__file__).resolve().parent)
if _init_dir not in sys.path:
    sys.path.insert(0, _init_dir)

from config import AiMemoryConfig  # noqa: E402
from provider import AiMemoryProvider  # noqa: E402


def register(ctx: object) -> None:
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    config = AiMemoryConfig()

    config_path = os.path.join(hermes_home, "ai-memory.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path) as f:
                overrides = json.load(f)
            for key in ("server_url", "api_key", "auth_token", "workspace", "project"):
                if key in overrides:
                    setattr(config, key, overrides[key])
        except (json.JSONDecodeError, OSError):
            pass

    for env_key, attr in (
        ("AI_MEMORY_SERVER_URL", "server_url"),
        ("AI_MEMORY_API_KEY", "api_key"),
        ("AI_MEMORY_AUTH_TOKEN", "auth_token"),
    ):
        val = os.environ.get(env_key)
        if val:
            setattr(config, attr, val)

    provider = AiMemoryProvider(config=config)
    ctx.register_memory_provider(provider)  # type: ignore[union-attr]
