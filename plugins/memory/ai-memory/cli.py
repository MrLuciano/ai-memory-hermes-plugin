from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from client import AiMemoryClient  # noqa: E402
from config import load_config  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="Show ai-memory server connection status")
    p.set_defaults(func=cmd_status)

    p = subparsers.add_parser("config", help="Show ai-memory plugin configuration")
    p.set_defaults(func=cmd_config)

    p = subparsers.add_parser("link", help="Link plugin into Hermes plugin directory")
    p.set_defaults(func=cmd_link)


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(args.hermes_home)
    client = AiMemoryClient(config)
    try:
        result = client.status()
        print("ai-memory server: reachable")
        print(f"  Pages:    {result.get('pages', '?')}")
        print(f"  Sessions: {result.get('sessions', '?')}")
    except Exception as e:
        print(f"ai-memory server: unreachable ({e})")


def cmd_config(args: argparse.Namespace) -> None:
    config = load_config(args.hermes_home)
    print("ai-memory configuration:")
    print(f"  server_url: {config.server_url}")
    print(f"  api_key:    {'****' if config.api_key else '(not set)'}")
    print(f"  auth_token: {'****' if config.auth_token else '(not set)'}")
    print(f"  workspace:  {config.workspace}")
    print(f"  project:    {config.project}")


def cmd_link(args: argparse.Namespace) -> None:
    target_dir = Path(args.hermes_home) / "plugins" / "ai-memory"
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        if os.path.islink(str(target_dir)):
            print(f"Already linked: {target_dir} -> {PLUGIN_DIR}")
        else:
            print(f"Target exists but is not a symlink: {target_dir}")
        return

    try:
        os.symlink(str(PLUGIN_DIR), str(target_dir), target_is_directory=True)
        print(f"Linked: {target_dir} -> {PLUGIN_DIR}")
    except FileExistsError:
        print(f"Already linked: {target_dir}")
    except OSError as e:
        print(f"Failed to link: {e}")
