from __future__ import annotations

import os
import sys
from pathlib import Path

_init_dir = str(Path(__file__).resolve().parent)
if _init_dir not in sys.path:
    sys.path.insert(0, _init_dir)

# Hermes loads __init__.py as a standalone module (not a package), so
# relative imports (from .foo import Bar) fail. Bare imports + sys.path
# ensure sibling modules are found regardless of how the plugin is loaded.
from config import load_config  # noqa: E402
from provider import AiMemoryProvider  # noqa: E402

__all__ = ["register"]


def _hermes_home() -> str:
    """Hermes home for ``register``, resolved the way Hermes resolves it.

    ``get_hermes_home()`` applies the context-local override, then
    ``HERMES_HOME``, then the platform default
    (hermes_constants.py:188-195), so the plugin agrees with the host. Fall
    back to the env/default pair when Hermes is not importable: the plugin
    must still load standalone (tests, CLI, a bare checkout).
    """
    try:
        from hermes_constants import get_hermes_home

        return str(get_hermes_home())
    except ImportError:
        return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def register(ctx: object) -> None:
    hermes_home = _hermes_home()
    # Share config validation/env precedence with initialize() and the CLI.
    config = load_config(hermes_home)

    provider = AiMemoryProvider(config=config)
    ctx.register_memory_provider(provider)  # type: ignore[union-attr]
