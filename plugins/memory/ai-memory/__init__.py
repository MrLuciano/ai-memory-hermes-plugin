from __future__ import annotations

import os

from config import AiMemoryConfig
from provider import AiMemoryProvider


def register(ctx: object) -> None:
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    config = AiMemoryConfig()

    config_path = os.path.join(hermes_home, "ai-memory.json")
    if os.path.isfile(config_path):
        import json

        try:
            with open(config_path) as f:
                overrides = json.load(f)
            for key in ("server_url", "api_key", "auth_token", "workspace", "project"):
                if key in overrides:
                    setattr(config, key, overrides[key])
        except Exception:
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
